import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import run

PAID = 'openrouter/test-only-paid'
MOCK = 'mockllm/model'


def setup_run(monkeypatch, tmp_path, usage, *, target=PAID, judge=PAID, controls=False):
    """Synthetic provider logs; this fixture cannot call a provider."""
    calls = []
    args = run.build_parser().parse_args([
        '--out', str(tmp_path), '--family', 'backup_care',
        '--target', target, '--judge', judge,
        '--ceiling-usd', '1', '--judge-cost-limit-usd', '0.05',
        *(['--controls'] if controls else []),
    ])

    def evaluate(task, *, model, **kwargs):
        calls.append(model)
        costs = usage if len(calls) == 1 else {model: 0.01}
        return [NS(
            eval=NS(model=model, task='synthetic', metadata={}, revision=None,
                    eval_id=f'synthetic-{len(calls)}'),
            stats=NS(model_usage={name: NS(total_cost=cost, model_dump=lambda cost=cost, **kw: {'total_cost': cost})
                                  for name, cost in costs.items()}),
            samples=[], status='success', location=f'synthetic-{len(calls)}.eval',
        )]

    monkeypatch.setattr(run, 'inspect_eval', evaluate)
    monkeypatch.setattr(run, 'conversation_family', lambda family: object())
    monkeypatch.setattr(run, 'target_samples', lambda location: ([object()], None))
    monkeypatch.setattr(run, 'target_judge', lambda *args, **kwargs: object())
    monkeypatch.setattr(run, 'control_judge', lambda **kwargs: object())
    return args, calls


@pytest.mark.parametrize('usage', [
    {}, {PAID: None}, {PAID: 0.01, 'other-paid': None}, {MOCK: None},
])
def test_unknown_paid_cost_prevents_next_paid_call_and_preserves_record(
    monkeypatch, tmp_path, usage,
):
    args, calls = setup_run(monkeypatch, tmp_path, usage)
    done, stop, error = run.execute(args)
    assert calls == [PAID]
    assert error is None
    assert stop == f'unknown paid cost before JUDGE backup_care {PAID}'
    run.write_record(args, done, stop)
    record = json.loads((tmp_path / 'run.json').read_text())
    assert record['stop_reason'] == stop
    assert len(record['logs']) == 1
    assert record['unknown_cost_logs'] == 1
    assert record['logs'][0]['model'] == PAID


def test_unknown_paid_control_stops_before_generation(monkeypatch, tmp_path):
    args, calls = setup_run(monkeypatch, tmp_path, {PAID: None}, controls=True)
    done, stop, error = run.execute(args)
    assert calls == [PAID]
    assert len(done) == 1 and done[0][0] == 'CTRL'
    assert stop == f'unknown paid cost before GEN backup_care {PAID}'
    assert error is None


@pytest.mark.parametrize('usage', [{}, {MOCK: None}])
def test_unknown_mock_cost_does_not_block_paid_judge(monkeypatch, tmp_path, usage):
    args, calls = setup_run(monkeypatch, tmp_path, usage, target=MOCK)
    done, stop, error = run.execute(args)
    assert calls == [MOCK, PAID]
    assert len(done) == 2 and stop is None and error is None


def test_known_paid_cost_and_unknown_mock_usage_do_not_block(monkeypatch, tmp_path):
    args, calls = setup_run(monkeypatch, tmp_path, {PAID: 0.01, MOCK: None})
    done, stop, error = run.execute(args)
    assert calls == [PAID, PAID]
    assert len(done) == 2 and stop is None and error is None


def test_unknown_paid_cost_allows_remaining_free_work(monkeypatch, tmp_path):
    args, calls = setup_run(monkeypatch, tmp_path, {PAID: None}, judge=MOCK)
    done, stop, error = run.execute(args)
    assert calls == [PAID, MOCK]
    assert len(done) == 2 and stop is None and error is None


def test_paid_usage_inside_mock_evaluation_still_blocks_next_paid_call(monkeypatch, tmp_path):
    args, calls = setup_run(monkeypatch, tmp_path, {PAID: None}, target=MOCK)
    done, stop, error = run.execute(args)
    assert calls == [MOCK]
    assert len(done) == 1 and error is None
    assert stop == f'unknown paid cost before JUDGE backup_care {MOCK}'


@pytest.mark.parametrize('controls', [False, True])
def test_cli_stop_keeps_native_log_and_completed_reports_without_network(
    monkeypatch, tmp_path, controls,
):
    """Only mock inference runs; rewrite the saved header to simulate missing paid cost."""
    import socket

    from inspect_ai.log import read_eval_log, write_eval_log
    from inspect_ai.model import ModelCost, ModelInfo, set_model_info

    # Inspect requires a price for the cost-limited control judge. Keep its
    # native guard and use a distinct, zero-cost mock; then simulate missing usage.
    mock_provider_name = 'mockllm/cost-policy-fixture'
    set_model_info(mock_provider_name, ModelInfo(cost=ModelCost(input=0.0, output=0.0, input_cache_write=0.0, input_cache_read=0.0)))
    real_evaluate = run.inspect_eval
    calls = []
    priced = 'openrouter/anthropic/claude-haiku-5.5'

    def mock_provider(task, **kwargs):
        calls.append(kwargs['model'])
        kwargs['model'] = mock_provider_name
        [log] = real_evaluate(task, **kwargs)
        log.eval.model = priced
        usage = next(iter(log.stats.model_usage.values()))
        usage.total_cost = None
        log.stats.model_usage = {priced: usage}
        write_eval_log(log, log.location)
        return [log]

    def forbid_network(*args, **kwargs):
        raise AssertionError('A proposed-policy test must never touch the network')

    monkeypatch.setattr(run, 'inspect_eval', mock_provider)
    monkeypatch.setattr(socket.socket, 'connect', forbid_network)
    out = tmp_path / 'run'
    args = [
        '--out', str(out), '--family', 'backup_care', '--target', priced, '--judge', priced,
        '--ceiling-usd', '1', '--judge-cost-limit-usd', '0.05',
        *(['--controls'] if controls else []),
    ]
    assert run.main(args) == 1
    assert calls == [priced]
    record = json.loads((out / 'run.json').read_text())
    [entry] = record['logs']
    saved = read_eval_log(entry['location'])
    assert saved.eval.model == entry['model'] == priced
    assert saved.stats.model_usage[priced].total_cost is None
    assert entry['model_usage'][priced]['total_cost'] is None
    assert saved.eval.eval_id == entry['eval_id']
    assert record['unknown_cost_logs'] == 1
    assert record['stop_reason'].startswith('unknown paid cost before ')
    if controls:
        stem = Path(entry['location']).stem
        reports = out / 'reports'
        assert (reports / f'{stem}.json').is_file()
        assert (reports / f'{stem}.md').is_file()
        assert not (out / 'generation').exists()
    else:
        assert not (out / 'judge').exists()
        assert not (out / 'reports').exists()

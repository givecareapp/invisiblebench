"""Jev (TypeSafe) as the judge, with a fake Jev: no test touches the network.

Jev answers one Choice question per judged sample. It returns a verdict and a probability
for each verdict, and no written reason or quotes.
"""
import json
import socket

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.model import get_model_info

import jev
import run
from grader import company, control_judge, control_samples
from task import ROOT

JEV = "typesafe/jev-1.14.0"


class FakeJev:
    """Answers every request with `choice` and records each request body and key."""

    def __init__(self):
        self.calls = []
        self.choice = "PASS"
        self.not_applicable = 0.1  # Noul: probability that the not_applicable rule holds

    def post(self, body, api_key):
        self.calls.append((body, api_key))
        answers = {}
        for name, question in body["questions"].items():
            if question["type"] == "choice":
                answers[name] = {
                    "type": "choice", "choice": self.choice, "confidence": 0.9,
                    "probabilities": {v: (0.96 if v == self.choice else 0.02)
                                      for v in question["criteria"]},
                }
            else:
                answers[name] = {"type": "noul", "noul": self.not_applicable}
        return {"model": body["model"], "answers": answers,
                "usage": {"input_tokens": 1000, "output_tokens": 12}}


@pytest.fixture
def fake_jev(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("A fake-Jev test must never touch the network")

    fake = FakeJev()
    monkeypatch.setattr(jev, "post_systemone", fake.post)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    return fake


def _sample(with_rule):
    """A backup_care sample whose criterion has, or lacks, a not_applicable rule."""
    return next(s for s in control_samples("backup_care")
                if ("not_applicable" in json.loads(s.input[-1].text)["criterion"]) == with_rule)


def test_without_a_not_applicable_rule_jev_chooses_among_three_verdicts():
    sample = _sample(with_rule=False)
    body = jev.request(sample.input)
    assert body["model"] == "jev-1.14.0"
    assert body["state"] == {k: v for k, v in json.loads(sample.input[-1].text).items()
                             if k != "criterion"}
    [(name, question)] = body["questions"].items()
    assert name == "verdict" and question["type"] == "choice"
    assert list(question["criteria"]) == ["PASS", "FAIL", "UNCLEAR"]
    # The judging rules carry over; the chat judge's JSON output format does not.
    assert "Judge this criterion only" in question["instructions"]["rules"]
    assert "Return only a JSON object" not in json.dumps(question)


def test_with_a_not_applicable_rule_applicability_is_its_own_question():
    # Asked together, Jev judged 90 NOT_APPLICABLE labels as PASS (7,512 judgments over three
    # rounds, 2026-11-12). Applicability is now a separate yes/no question over the same state.
    body = jev.request(_sample(with_rule=True).input)
    assert set(body["questions"]) == {"verdict", "not_applicable"}
    assert list(body["questions"]["verdict"]["criteria"]) == ["PASS", "FAIL", "UNCLEAR"]
    question = body["questions"]["not_applicable"]
    assert question["type"] == "noul"
    assert "`criterion.not_applicable`" in question["instructions"]["question"]


@pytest.mark.parametrize("probability, verdict", [(0.8, "NOT_APPLICABLE"), (0.2, "PASS")])
def test_the_applicability_answer_decides_not_applicable_in_code(probability, verdict):
    answer = {"type": "choice", "choice": "PASS", "confidence": 0.9,
              "probabilities": {"PASS": 0.9, "FAIL": 0.05, "UNCLEAR": 0.05},
              "not_applicable": probability}
    parsed = jev.parse_answer(json.dumps(answer))
    assert parsed["verdict"] == verdict and parsed["not_applicable"] == probability


def test_a_fake_jev_verdict_is_scored_with_its_probabilities(fake_jev, tmp_path):
    fake_jev.choice = "FAIL"
    task = control_judge(cost_limit_usd=0.05)
    [log] = inspect_eval(task, model=JEV, limit=2, log_dir=str(tmp_path), display="none")
    assert log.status == "success"
    body, key = fake_jev.calls[0]
    assert len(fake_jev.calls) == 2  # one request per judged sample
    assert key == "test-key" and body["model"] == "jev-1.14.0"
    for sample in log.samples:
        [score] = sample.scores.values()
        assert score.value == "FAIL"
        assert score.metadata["evidence"]["probabilities"]["FAIL"] == 0.96
        assert score.metadata["evidence"]["judge"] == "jev-1.14.0"
    [usage] = log.stats.model_usage.values()
    assert usage.input_tokens == 2000
    assert usage.total_cost == pytest.approx(2000 * 0.042 / 1_000_000)


@pytest.mark.parametrize("usage", [None, {}, {"input_tokens": 1000}, {"output_tokens": 12}])
def test_missing_jev_usage_stays_unknown_even_beside_a_priced_sample(
    fake_jev, monkeypatch, tmp_path, usage,
):
    post = fake_jev.post

    def incomplete_usage(body, api_key):
        reply = post(body, api_key)
        if len(fake_jev.calls) == 1:
            reply["usage"] = usage
        return reply

    monkeypatch.setattr(jev, "post_systemone", incomplete_usage)
    [log] = inspect_eval(control_judge(cost_limit_usd=0.05), model=JEV, limit=2,
                         max_connections=1, log_dir=str(tmp_path), display="none")
    assert log.status == "success"
    assert all(next(iter(s.scores.values())).value == "PASS" for s in log.samples)
    # The valid answer survives, but its unknown cost must block the next paid eval.
    assert sum(s.output.usage is None for s in log.samples) == 1
    assert run.unknown_paid_cost(log)
    cost, unknown = run.reported_cost([log])
    assert cost == pytest.approx(1000 * 0.042 / 1_000_000)
    assert unknown == 1


@pytest.mark.parametrize("answer, message", [
    ({"type": "choice", "choice": "MAYBE", "confidence": 1.0,
      "probabilities": {"MAYBE": 1.0}}, "Unknown verdict"),
    ({"type": "noul", "noul": 0.9}, "Expected a choice answer"),
])
def test_a_malformed_jev_answer_is_unscored(answer, message):
    with pytest.raises(ValueError, match=message):
        jev.parse_answer(json.dumps(answer))


def test_only_the_pinned_jev_is_priced_and_accepted():
    assert get_model_info(JEV).cost.input == 0.042
    assert get_model_info(JEV).cost.output == 0.0
    assert company(JEV) == "typesafe"
    with pytest.raises(ValueError, match="pinned"):
        jev.request(control_samples("backup_care")[0].input, model="jev-latest")


class EvalCalled(Exception):
    pass


def test_the_runner_accepts_jev_as_a_priced_judge(tmp_path, monkeypatch):
    def evaluation(*args, **kwargs):
        raise EvalCalled

    monkeypatch.setattr(run, "inspect_eval", evaluation)
    with pytest.raises(EvalCalled):
        run.main(["--out", str(tmp_path / "run"), "--family", "backup_care", "--controls",
                  "--judge", JEV, "--judge-cost-limit-usd", "0.05", "--ceiling-usd", "1"])
    assert (ROOT / "jev.py").is_file()


def test_a_fake_jev_applicability_answer_reaches_the_score(fake_jev, tmp_path):
    fake_jev.not_applicable = 0.9
    sample = _sample(with_rule=True)
    task = control_judge(cost_limit_usd=0.05)
    [log] = inspect_eval(task, model=JEV, sample_id=str(sample.id), log_dir=str(tmp_path),
                         display="none")
    [scored] = log.samples
    [score] = scored.scores.values()
    assert score.value == "NOT_APPLICABLE"
    assert score.metadata["evidence"]["not_applicable"] == 0.9
    assert score.metadata["evidence"]["choice"] == "PASS"


def test_single_and_batch_use_identical_state_and_question_content():
    from grader import batch_samples

    samples = [s for s in control_samples('backup_care')
               if s.id.startswith('supported_confirmed/') and s.metadata['turn'] == 2]
    [batch], _ = batch_samples(samples)
    grouped = jev.request(batch.input)
    for sample in samples:
        single = jev.request(sample.input)
        assert single['state'] == grouped['state']
        check = sample.metadata['check']
        for name, question in single['questions'].items():
            assert question == grouped['questions'][f'{check}.{name}']


def test_each_jev_question_has_evidence_rules_and_only_its_own_answer_space():
    from grader import batch_samples

    sample = _sample(with_rule=True)
    [batch], _ = batch_samples([sample])
    for body in (jev.request(sample.input), jev.request(batch.input)):
        for question in body['questions'].values():
            instructions = str(question['instructions'])
            assert 'untrusted evidence' in instructions
            assert 'Use NOT_APPLICABLE' not in instructions
            if question['type'] == 'noul':
                assert 'Use UNCLEAR' not in instructions


@pytest.mark.parametrize('change', [
    {'not_applicable': None}, {'not_applicable': True},
    {'not_applicable': float('nan')},
    {'probabilities': {'PASS': 2.0, 'FAIL': -1.0, 'UNCLEAR': 0.0}},
    {'probabilities': {'PASS': True, 'FAIL': 0.0, 'UNCLEAR': 0.0}},
    {'probabilities': {'PASS': 0.9, 'FAIL': 0.9, 'UNCLEAR': 0.9}},
    {'confidence': None}, {'confidence': True},
])
def test_invalid_probabilities_are_not_verdicts(change):
    answer = {'type': 'choice', 'choice': 'PASS', 'confidence': 0.85,
              'probabilities': {'PASS': 0.9, 'FAIL': 0.05, 'UNCLEAR': 0.05},
              'not_applicable': 0.1, **change}
    with pytest.raises(ValueError):
        jev.parse_answer(json.dumps(answer))


@pytest.mark.parametrize('batch', [False, True])
@pytest.mark.parametrize('fault', ['missing_noul', 'null_noul', 'boolean_noul',
                                   'wrong_type', 'invalid_probability', 'missing_confidence'])
def test_invalid_answer_keeps_usage_and_stays_unscored(fake_jev, monkeypatch, tmp_path, batch, fault):
    from report import build_report

    original = fake_jev.post

    def damage(body, key):
        reply = original(body, key)
        prefix = 'care.fit.' if batch else ''
        noul = prefix + 'not_applicable'
        choice = prefix + 'verdict'
        if fault == 'missing_noul':
            del reply['answers'][noul]
        elif fault == 'null_noul':
            reply['answers'][noul]['noul'] = None
        elif fault == 'boolean_noul':
            reply['answers'][noul]['noul'] = True
        elif fault == 'wrong_type':
            reply['answers'][noul]['type'] = 'score'
        elif fault == 'invalid_probability':
            reply['answers'][choice]['probabilities']['PASS'] = 2
        else:
            del reply['answers'][choice]['confidence']
        return reply

    monkeypatch.setattr(jev, 'post_systemone', damage)
    sample_id = 'supported_confirmed/turn-2' if batch else 'supported_confirmed/care.fit@2'
    [log] = inspect_eval(control_judge(0.05, batch=batch), model=JEV, sample_id=sample_id,
                         log_dir=str(tmp_path), display='none')
    assert log.status == 'success'
    assert len(log.samples) == 1 and log.samples[0].error is None
    assert log.samples[0].output.usage.input_tokens == 1000
    assert 'answers' in json.loads(log.samples[0].output.completion)
    trials = build_report(log)['trials']
    assert [t['check'] for t in trials if t['verdict'] is None] == ['care.fit']
    assert all(t['verdict'] == 'PASS' for t in trials if t['check'] != 'care.fit')
    assert not run.unknown_paid_cost(log)


def test_historical_flattened_answer_remains_readable_and_requires_its_noul():
    answer = {'type': 'choice', 'choice': 'PASS', 'confidence': 0.85,
              'probabilities': {'PASS': 0.9, 'FAIL': 0.05, 'UNCLEAR': 0.05},
              'not_applicable': 0.1, 'judge': 'jev-1.14.0'}
    assert jev.parse_response(json.dumps(answer), with_rule=True,
                              model='jev-1.14.0')['verdict'] == 'PASS'
    del answer['not_applicable']
    with pytest.raises(ValueError, match='not_applicable'):
        jev.parse_response(json.dumps(answer), with_rule=True, model='jev-1.14.0')
    assert jev.parse_response(json.dumps(answer), with_rule=False,
                              model='jev-1.14.0')['verdict'] == 'PASS'


@pytest.mark.parametrize('batch', [False, True])
@pytest.mark.parametrize('returned_model', [None, 'jev-1.13.0'])
def test_wrong_response_model_is_unscored_without_losing_usage(
    fake_jev, monkeypatch, tmp_path, batch, returned_model,
):
    from report import build_report

    original = fake_jev.post

    def damage(body, key):
        reply = original(body, key)
        if returned_model is None:
            del reply['model']
        else:
            reply['model'] = returned_model
        return reply

    monkeypatch.setattr(jev, 'post_systemone', damage)
    sample_id = 'supported_confirmed/turn-1' if batch else 'supported_confirmed/agency.consent@1'
    [log] = inspect_eval(control_judge(0.05, batch=batch), model=JEV, sample_id=sample_id,
                         log_dir=str(tmp_path), display='none')
    assert log.status == 'success' and log.samples[0].error is None
    raw = json.loads(log.samples[0].output.completion)
    assert raw.get('model') == returned_model
    assert log.samples[0].output.usage.input_tokens == 1000
    trials = build_report(log)['trials']
    assert len(trials) == (6 if batch else 1)
    assert all(t['verdict'] is None and 'model' in t['unscored_reason'] for t in trials)
    assert not run.unknown_paid_cost(log)


@pytest.mark.parametrize('batch', [False, True])
def test_unrequested_applicability_cannot_remove_a_check(
    fake_jev, monkeypatch, tmp_path, batch,
):
    from report import build_report

    original = fake_jev.post

    def damage(body, key):
        reply = original(body, key)
        choice = 'agency.consent.verdict' if batch else 'verdict'
        reply['answers'][choice]['not_applicable'] = 1.0
        return reply

    monkeypatch.setattr(jev, 'post_systemone', damage)
    sample_id = 'supported_confirmed/turn-1' if batch else 'supported_confirmed/agency.consent@1'
    [log] = inspect_eval(control_judge(0.05, batch=batch), model=JEV, sample_id=sample_id,
                         log_dir=str(tmp_path), display='none')
    assert log.status == 'success' and log.samples[0].error is None
    raw = json.loads(log.samples[0].output.completion)
    choice = 'agency.consent.verdict' if batch else 'verdict'
    assert raw['answers'][choice]['not_applicable'] == 1.0
    assert log.samples[0].output.usage.input_tokens == 1000
    trials = build_report(log)['trials']
    assert [t['check'] for t in trials if t['verdict'] is None] == ['agency.consent']
    assert all(t['verdict'] == 'PASS' for t in trials if t['check'] != 'agency.consent')
    assert not run.unknown_paid_cost(log)

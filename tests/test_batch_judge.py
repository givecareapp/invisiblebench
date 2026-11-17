"""Real Inspect tasks with a fake HTTP boundary. No inference or network access."""

import json
import subprocess
import sys
from copy import deepcopy

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.log import read_eval_log
from test_jev import JEV

import jev
import run
from grader import control_judge, judged_samples, summarize, target_judge
from release import build_results, load_run, record_run
from report import build_jury_card, build_report, diff_reports, summarize_rows, target_rows
from review_packet import build_packet
from task import ROOT, conversation_family

pytest_plugins = ["test_jev"]


def evaluate(task, path, **kwargs):
    [log] = inspect_eval(task, model=JEV, log_dir=str(path), display="none",
                         max_connections=1, **kwargs)
    assert log.status == "success"
    return read_eval_log(log.location)


def test_control_batches_preserve_checks_reports_and_charge_one_request(fake_jev, tmp_path):
    task = control_judge(0.05, batch=True)
    logical_count = sum(len(s.metadata["checks"]) for s in list(task.dataset)[:3])
    batched = evaluate(task, tmp_path / "batch", limit=3)
    assert len(fake_jev.calls) == 3
    [usage] = batched.stats.model_usage.values()
    assert usage.input_tokens == 3000
    assert usage.total_cost == pytest.approx(3000 * 0.042 / 1_000_000)
    assert len(list(judged_samples(batched))) == logical_count
    assert not hasattr(next(judged_samples(batched)), "output")
    for body, _ in fake_jev.calls:
        assert set(body["state"]) == {"response_turn", "conversation"}
        assert body["state"]["conversation"][-1]["turn"] == body["state"]["response_turn"]
        for question in body["questions"].values():
            instructions = question["instructions"]
            assert {"state_guide", "criterion", "question"} <= set(instructions)
            if question["type"] == "choice":
                assert "Judge this criterion only" in instructions["rules"]
            else:
                assert "rules" not in instructions
                assert instructions["criterion"]["not_applicable"]
            assert "expected" not in json.dumps(question)
            assert "dimension" not in instructions["criterion"]
            assert "protects" not in instructions["criterion"]
    fake_jev.calls.clear()
    single = evaluate(control_judge(0.05), tmp_path / "single", limit=logical_count)
    assert len(fake_jev.calls) == logical_count
    trials = build_report(batched)["trials"]
    assert all(t["request_sample_id"] in {s.id for s in batched.samples} for t in trials)
    assert [{k: v for k, v in t.items() if k != "request_sample_id"} for t in trials] == (
        build_report(single)["trials"])
    assert summarize(batched)["by_layer"] == summarize(single)["by_layer"]
    diff = diff_reports(build_report(single), build_report(batched))
    assert diff["paired"] == logical_count and not diff["flips"]
    assert diff["only_before"] == diff["only_after"] == 0
    wrong = deepcopy(build_report(single))
    wrong["run"]["cohort_sha256"] = "different"
    with pytest.raises(ValueError, match="same frozen cohort"):
        diff_reports(wrong, build_report(batched))


@pytest.mark.parametrize("fault", ["missing_choice", "malformed_choice", "missing_noul",
                                   "malformed_noul", "invalid_probability"])
def test_one_bad_question_keeps_other_results_and_usage(fake_jev, tmp_path, monkeypatch, fault):
    post = fake_jev.post
    broken = []

    def damage(body, key):
        reply = post(body, key)
        name = next(n for n in body["questions"] if n.endswith(".not_applicable"))
        check = name.removesuffix(".not_applicable")
        broken.append(check)
        if fault == "missing_choice":
            del reply["answers"][f"{check}.verdict"]
        elif fault == "malformed_choice":
            reply["answers"][f"{check}.verdict"] = {"type": "choice", "choice": "MAYBE"}
        elif fault == "missing_noul":
            del reply["answers"][name]
        elif fault == "malformed_noul":
            reply["answers"][name]["noul"] = None
        else:
            reply["answers"][f"{check}.verdict"]["probabilities"]["PASS"] = True
        return reply

    monkeypatch.setattr(jev, "post_systemone", damage)
    log = evaluate(control_judge(0.05, batch=True), tmp_path, limit=1)
    trials = build_report(log)["trials"]
    assert len(broken) == 1
    assert [t["check"] for t in trials if t["verdict"] is None] == broken
    assert all(t["verdict"] == "PASS" for t in trials if t["check"] not in broken)
    assert not run.unknown_paid_cost(log)


def test_batch_repeats_are_fresh_requests_and_missing_usage_stays_unknown(
    fake_jev, tmp_path, monkeypatch,
):
    post = fake_jev.post

    def missing_usage(body, key):
        reply = post(body, key)
        if len(fake_jev.calls) == 1:
            del reply["usage"]
        return reply

    monkeypatch.setattr(jev, "post_systemone", missing_usage)
    log = evaluate(control_judge(0.05, batch=True), tmp_path, limit=1, epochs=2)
    assert len(fake_jev.calls) == 2
    assert {s.epoch for s in judged_samples(log)} == {1, 2}
    assert run.unknown_paid_cost(log)
    assert run.reported_cost([log])[1] == 1
    assert all(t["verdict"] == "PASS" for t in build_report(log)["trials"])


def test_target_batch_reports_release_and_review_ids_match_single_checks(fake_jev, tmp_path):
    [generation] = inspect_eval(conversation_family(), model="mockllm/model",
                                log_dir=str(tmp_path / "generation"), display="none", epochs=2)
    batch_task = target_judge(generation.location, 0.05, batch=True)
    # Two source repeats remain separate even though their mocked replies are identical.
    assert len(batch_task.dataset) == 18
    logical_count = sum(len(s.metadata["checks"]) for s in list(batch_task.dataset)[:2])
    batched = evaluate(batch_task, tmp_path / "batch", limit=2)
    single = evaluate(target_judge(generation.location, 0.05), tmp_path / "single",
                      limit=logical_count)
    rows = target_rows(batched)
    assert [{k: v for k, v in r.items() if k != "judge_method"} for r in rows] == [
        {k: v for k, v in r.items() if k != "judge_method"} for r in target_rows(single)]
    with pytest.raises(ValueError, match="different judge methods"):
        summarize_rows(rows + target_rows(single))
    assert len(target_rows(batched)) == 108
    card = build_jury_card([batched])
    assert card.pop("judge_method") == jev.BATCH_METHOD
    for row in card["verdicts"]:
        assert row.pop("request_sample_id") in {s.id for s in batched.samples}
    assert card == build_jury_card([single])
    with pytest.raises(ValueError, match="different judge methods"):
        build_jury_card([batched, single])
    assert record_run([batched], "batch")["verdicts"] == record_run([single], "single")["verdicts"]
    packet = build_packet(generation.location)
    packet_ids = {item["item_id"] for item in packet["items"]}
    assert {t["sample_id"] for t in build_report(batched)["trials"]} <= packet_ids
    missing = deepcopy(batched)
    missing.samples.pop()
    assert len(target_rows(missing)) == 108
    assert sum(r["verdict"] is not None for r in target_rows(missing)) < logical_count


def test_complete_runner_writes_reports_without_changing_public_release(fake_jev, tmp_path):
    out = tmp_path / "run"
    assert run.main([
        "--out", str(out), "--family", "backup_care", "--controls", "--batch-judge",
        "--judge", JEV, "--target", "mockllm/model",
        "--judge-cost-limit-usd", "0.05", "--ceiling-usd", "1",
    ]) == 0
    assert len(fake_jev.calls) == 72 + 9
    logs = load_run(out)
    [log] = logs
    assert len(log.samples) == 9
    assert len(target_rows(log)) == 54
    assert all(r["verdict"] == "PASS" for r in target_rows(log))
    assert json.loads((out / "reports" / "summary.json").read_text())["unscored"] == 0
    record = record_run(logs, "batch")
    assert record["run"]["judge_method"] == jev.BATCH_METHOD
    changes = [{"date": "2026-11-17", "version": record["run"]["benchmark_version"],
                "status": "development", "runs": ["batch"], "text": "Experimental."}]
    with pytest.raises(ValueError, match="public release contract"):
        build_results(changes, {"batch": record})


@pytest.mark.parametrize("damage", ["metadata", "duplicate", "omitted_check", "extra_score"])
def test_batch_reader_rejects_broken_provenance(fake_jev, tmp_path, damage):
    log = evaluate(control_judge(0.05, batch=True), tmp_path, limit=1)
    sample = log.samples[0]
    if damage == "metadata":
        next(iter(sample.metadata["checks"].values()))["turn"] = 99
    elif damage == "duplicate":
        log.samples.append(sample)
    elif damage == "omitted_check":
        next(iter(log.eval.metadata["batch_manifest"].values())).pop()
    else:
        sample.scores["extra"] = next(iter(sample.scores.values()))
    with pytest.raises(ValueError):
        build_report(log)


def test_runner_rejects_batching_for_a_chat_judge_before_execution(tmp_path):
    args = run.build_parser().parse_args([
        "--out", str(tmp_path), "--family", "backup_care", "--controls",
        "--judge", "mockllm/model", "--batch-judge",
    ])
    with pytest.raises(ValueError, match="requires typesafe"):
        run.check_request(args)


def test_whole_request_error_stays_visible_for_every_check(fake_jev, tmp_path, monkeypatch):
    calls = []

    def fail(body, key):
        calls.append(body)
        raise RuntimeError("Synthetic HTTP failure")

    monkeypatch.setattr(jev, "post_systemone", fail)
    [log] = inspect_eval(control_judge(0.05, batch=True), model=JEV, limit=1,
                         fail_on_error=False, log_dir=str(tmp_path), display="none")
    assert len(calls) == len(log.samples) == 1
    report = build_report(log)
    assert all(t["verdict"] is None and t["execution_error"] for t in report["trials"])
    assert sum(c["execution_error"] for layer in report["summary"]["by_layer"].values()
               for c in layer.values()) == len(report["trials"])
    assert run.unknown_paid_cost(log)


def test_all_missing_answers_are_unscored_but_keep_request_usage(fake_jev, tmp_path, monkeypatch):
    post = fake_jev.post

    def empty(body, key):
        reply = post(body, key)
        reply["answers"] = None
        return reply

    monkeypatch.setattr(jev, "post_systemone", empty)
    log = evaluate(control_judge(0.05, batch=True), tmp_path, limit=1)
    trials = build_report(log)["trials"]
    assert trials and all(t["verdict"] is None and not t["execution_error"] for t in trials)
    assert not run.unknown_paid_cost(log)


def test_answers_dispatch_by_check_even_when_reordered(fake_jev, tmp_path, monkeypatch):
    post = fake_jev.post
    expected = {}

    def distinct(body, key):
        reply = post(body, key)
        for index, (name, question) in enumerate(body["questions"].items()):
            check, kind = name.rsplit(".", 1)
            if kind == "verdict":
                verdict = ["PASS", "FAIL", "UNCLEAR"][index % 3]
                reply["answers"][name].update(
                    choice=verdict,
                    probabilities={v: (0.96 if v == verdict else 0.02)
                                   for v in question["criteria"]})
                expected[check] = verdict
            else:
                reply["answers"][name]["noul"] = 0.9
                expected[check] = "NOT_APPLICABLE"
        reply["answers"] = dict(reversed(list(reply["answers"].items())))
        return reply

    monkeypatch.setattr(jev, "post_systemone", distinct)
    log = evaluate(control_judge(0.05, batch=True), tmp_path, limit=1)
    assert len(set(expected.values())) > 1
    assert {t["check"]: t["verdict"] for t in build_report(log)["trials"]} == expected


def test_native_scorers_can_be_reconstructed_in_a_fresh_process(fake_jev, tmp_path):
    log = evaluate(control_judge(0.05, batch=True), tmp_path, limit=2)
    output = tmp_path / "rescored.eval"
    # Only trusted synthetic logs. A child process also forbids network and transport.
    script = """
import socket, sys
import jev
from inspect_ai._cli.main import main
def forbidden(*args, **kwargs):
    raise AssertionError('Re-scoring must not invoke a model or the network')
socket.socket.connect = forbidden
jev.post_systemone = forbidden
sys.argv = ['inspect', 'score', sys.argv[1], '--action', 'overwrite',
            '--output-file', sys.argv[2], '--display', 'none']
main()
"""
    result = subprocess.run([sys.executable, "-c", script, log.location, str(output)],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    reread = read_eval_log(str(output))
    assert build_report(reread)["trials"] == build_report(log)["trials"]
    assert [s.model_dump() for s in reread.results.scores] == [
        s.model_dump() for s in log.results.scores]

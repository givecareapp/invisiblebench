"""A paired comparison must keep failures, missing coverage and exact input identity."""

import json
import sys
from copy import deepcopy

import pytest
from test_batch_judge import evaluate

from grader import control_judge
from report import build_report, diff_reports, main, render_diff

pytest_plugins = ["test_jev"]


@pytest.fixture
def paired_logs(fake_jev, tmp_path):
    before = evaluate(control_judge(0.05), tmp_path / "single", limit=6)
    after = evaluate(control_judge(0.05, batch=True), tmp_path / "batch", limit=1)
    return before, after


def compare(logs):
    return diff_reports(*(build_report(log) for log in logs))


def test_agreement_keeps_full_denominator_and_physical_usage(paired_logs):
    diff = compare(paired_logs)
    assert diff["paired"] == 6 and not diff["flips"]
    assert sum(c["planned"] for c in diff["by_check"]) == 450
    assert sum(c["both_scored"] for c in diff["by_check"]) == 6
    assert sum(c["same_verdict"] for c in diff["by_check"]) == 6
    assert sum(c["missing_both"] for c in diff["by_check"]) == 450 - 6
    assert {c["layer"] for c in diff["by_check"]} == {"Safety", "Care"}
    a, b = (diff[side]["execution"] for side in ("before", "after"))
    assert (a["native_samples"], b["native_samples"]) == (6, 1)
    assert next(iter(a["model_usage"].values()))["input_tokens"] == 6000
    assert next(iter(b["model_usage"].values()))["input_tokens"] == 1000
    assert a["wall_seconds"] >= 0 and b["wall_seconds"] >= 0


def test_lost_answer_and_new_false_failure_are_separate(paired_logs):
    before, after = paired_logs
    sample = after.samples[0]
    scheduled = [(name, score) for name, score in sample.scores.items()
                 if score.reason != "not_scheduled"]
    failed_name, failed = next((n, s) for n, s in scheduled if s.metadata["expected"] == "PASS")
    failed.value = "FAIL"
    lost_name, lost = next((n, s) for n, s in scheduled if n != failed_name)
    del sample.scores[lost_name]
    sample.output.usage = None
    diff = compare((before, after))
    failure = next(c for c in diff["by_check"] if c["check"] == failed.metadata["check"])
    assert failure["verdict_changes"] == 1
    assert failure["after"]["false_fail"] == failure["before"]["false_fail"] + 1
    loss = next(c for c in diff["by_check"] if c["check"] == lost.metadata["check"])
    assert loss["lost_verdict"] == loss["after"]["unscored"] == 1
    assert loss["verdict_changes"] == 0
    assert diff["coverage_changes"][0]["before"] == "scored"
    assert diff["coverage_changes"][0]["after"] == "unscored"
    assert diff["after"]["execution"]["samples_without_usage"] == 1


def test_no_records_cannot_look_like_full_agreement(paired_logs):
    for log in paired_logs:
        log.samples = []
    diff = compare(paired_logs)
    assert not diff["flips"] and diff["paired"] == 0
    assert sum(c["both_scored"] for c in diff["by_check"]) == 0
    assert sum(c["missing_both"] for c in diff["by_check"]) == 450
    text = render_diff(diff)
    assert "Missing and unscored checks are not agreements" in text
    assert "Check scored coverage above" in text


def test_missing_batch_is_lost_coverage_not_a_verdict_change(paired_logs):
    paired_logs[1].samples = []
    diff = compare(paired_logs)
    assert not diff["flips"]
    assert diff["only_before"] == 6
    assert sum(c["lost_verdict"] for c in diff["by_check"]) == 6
    assert sum(c["verdict_changes"] for c in diff["by_check"]) == 0
    assert len(diff["coverage_changes"]) == 6
    assert all(c["after"] == "missing" for c in diff["coverage_changes"])


def test_matching_ids_do_not_permit_changed_reply_or_rule(paired_logs):
    before, original = paired_logs
    for change in ("reply", "criterion"):
        after = deepcopy(original)
        sample = after.samples[0]
        payload = json.loads(sample.input[-1].text)
        if change == "reply":
            payload["state"]["conversation"][-1]["content"] += " Changed reply."
        else:
            check = next(c for c, rule in payload["criteria"].items() if not rule.get("subchecks"))
            payload["criteria"][check]["question"] += " Changed rule."
            payload["questions"][f"{check}.verdict"]["instructions"]["question"] += " Changed rule."
        sample.input[-1].content = json.dumps(payload)
        with pytest.raises(ValueError, match="same frozen criterion and conversation"):
            compare((before, after))


def test_method_comparison_requires_effective_generation_settings(paired_logs):
    before, original = paired_logs
    for field, value in (("temperature", 0.7), ("max_connections", 2)):
        after = deepcopy(original)
        setattr(after.plan.config, field, value)
        with pytest.raises(ValueError, match="model and settings fixed"):
            compare((before, after))


def test_version_and_duplicate_checks_cannot_be_silently_paired(paired_logs):
    before, after = (build_report(log) for log in paired_logs)
    changed = deepcopy(after)
    changed["run"]["benchmark_version"] = "999.0.0"
    with pytest.raises(ValueError, match="same benchmark version"):
        diff_reports(before, changed)
    after["trials"].append(after["trials"][0])
    with pytest.raises(ValueError, match="Duplicate check"):
        diff_reports(before, after)


def test_cli_renders_a_markdown_comparison_from_native_logs(paired_logs, monkeypatch, capsys):
    before, after = paired_logs
    monkeypatch.setattr(sys, "argv", ["report.py", after.location, "--diff", before.location,
                                      "--format", "markdown"])
    main()
    text = capsys.readouterr().out
    assert "# Paired judge comparison" in text
    assert "Scored before → after" in text
    assert "False pass before → after" in text
    assert "criterion/v1" in text and "jev-prefix-batch/v1" in text

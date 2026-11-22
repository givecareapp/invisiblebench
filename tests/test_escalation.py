"""Offline System Two cross-company escalation tests: no network calls."""

import json
from glob import glob

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.model import ModelOutput, get_model

import run
from grader import escalate_judge, escalation_samples, target_judge
from report import build_report, render_markdown
from task import conversation_family

pytest_plugins = ["test_jev"]


def _system_one_log(fake_jev, tmp_path):
    gen_dir = tmp_path / "gen"
    [gen] = inspect_eval(
        conversation_family("backup_care"), model="mockllm/model",
        sample_id="backup_care/confirmed", log_dir=str(gen_dir), display="none",
    )
    # Force one UNCLEAR (0.50) and leave the rest PASS (0.96).
    fake_jev.overrides["verdict"] = 0.50
    task = target_judge(gen.location, cost_limit_usd=0.05)
    [judged] = inspect_eval(
        task, model="typesafe/jev-1.14.0",
        sample_id=[str(task.dataset[0].id), str(task.dataset[2].id)],
        log_dir=str(tmp_path / "judge"), display="none",
    )
    return judged


def test_escalation_selects_unclear_and_optional_safety_and_verifies_quotes(fake_jev, tmp_path):
    judged = _system_one_log(fake_jev, tmp_path)
    # task.dataset[0] is Care coverage.status@1 (UNCLEAR 0.50); dataset[2] is Safety agency.consent@1 (PASS 0.96).
    uncertain, policy = escalation_samples(judged.location, include_safety=False, close_below=0.65)
    assert len(uncertain) == 1
    assert uncertain[0].metadata["check"] == "coverage.status"
    assert "unclear" in uncertain[0].metadata["escalation_reasons"]
    assert policy["policy"]["selected_checks"] == 1

    with_safety, policy_s = escalation_samples(judged.location, include_safety=True, close_below=0.65)
    assert len(with_safety) == 2
    assert {s.metadata["check"] for s in with_safety} == {"coverage.status", "agency.consent"}
    # Subchecks are stripped for System Two canonical chat evaluation.
    for sample in with_safety:
        prompt = json.loads(sample.input[-1].text)
        assert "subchecks" not in prompt["criterion"]
    assert policy_s["policy"]["include_safety"] is True

    def chat_judge(messages, tools, tool_choice, config):
        prompt = json.loads(messages[-1].text)
        convo = prompt["conversation"]
        return ModelOutput.from_content("mockllm/model", json.dumps({
            "verdict": "FAIL",
            "reason": "System Two identified an issue.",
            "response_quote": convo[-1]["content"],
            "cue_turn": prompt["response_turn"],
            "cue_quote": convo[-2]["content"],
        }))

    esc_task = escalate_judge(judged.location, include_safety=True, close_below=0.65)
    [esc_log] = inspect_eval(
        esc_task, model=get_model("mockllm/model", custom_outputs=chat_judge),
        log_dir=str(tmp_path / "escalate"), display="none",
    )
    assert esc_log.status == "success"
    report = build_report(esc_log)
    assert report["kind"] == "target-escalation-audit"
    assert report["summary"]["flip_counts"] == {"PASS->FAIL": 1, "UNCLEAR->FAIL": 1}
    assert report["summary"]["parent_judge"]["eval_id"] == judged.eval.eval_id
    md = render_markdown(report)
    assert "## System Two escalation audit" in md
    assert "PASS → FAIL" in md and "UNCLEAR → FAIL" in md
    assert "System Two identified an issue." in md


def test_runner_escalate_judge_gates_same_company_and_runs_end_to_end(tmp_path, capsys):
    # Same company as primary judge or target is refused before any eval.
    with pytest.raises(SystemExit) as refused:
        run.main([
            "--out", str(tmp_path / "bad1"), "--family", "backup_care",
            "--target", "openrouter/openai/gpt-5.6-luna",
            "--judge", "typesafe/jev-1.14.0",
            "--escalate-judge", "openrouter/openai/gpt-5.6-luna-pro",
            "--judge-cost-limit-usd", "0.05", "--ceiling-usd", "1",
        ])
    assert refused.value.code == 2
    assert "escalation judge" in capsys.readouterr().err

    # Free mock end-to-end run: GEN -> JUDGE (unscored mock) -> ESCALATE (all unscored checks).
    out = tmp_path / "e2e"
    assert run.main([
        "--out", str(out), "--family", "backup_care",
        "--target", "mockllm/model", "--judge", "mockllm/model",
        "--escalate-judge", "mockllm/other",
    ]) == 0
    record = json.loads((out / "run.json").read_text())
    assert [e["task"] for e in record["logs"]] == [
        "conversation_family", "target_judge", "escalate_judge",
    ]
    assert record["logs"][0]["generation_config"]["max_tokens"] == 8192
    assert glob(str(out / "escalate/*.eval"))
    esc_reports = [
        json.loads(p.read_text()) for p in (out / "reports").glob("*.json")
        if p.name not in ("summary.json", "jury-card.json")
    ]
    assert any(r["kind"] == "target-escalation-audit" for r in esc_reports)

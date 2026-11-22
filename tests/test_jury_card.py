import json
from glob import glob

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.model import ModelOutput, get_model

from grader import target_judge
from report import REASON, build_jury_card, build_report, render_jury_card, render_markdown
from task import conversation_family


def _judged(tmp_path):
    """A mock generation judged by a mock JSON judge, then given Jev-shaped evidence."""
    generation_dir = tmp_path / "generation"
    inspect_eval(conversation_family("backup_care"), model="mockllm/model",
                 sample_id="backup_care/confirmed", log_dir=str(generation_dir), display="none")
    task = target_judge(glob(str(generation_dir / "*.eval"))[0])

    def judgment(messages, tools, tool_choice, config):
        prompt = json.loads(messages[-1].text)
        conversation = prompt["conversation"]
        return ModelOutput.from_content("mockllm/model", json.dumps({
            "verdict": "PASS", "reason": "Fits.", "response_quote": conversation[-1]["content"],
            "cue_turn": prompt["response_turn"], "cue_quote": conversation[-2]["content"]}))

    [log] = inspect_eval(task, model=get_model("mockllm/model", custom_outputs=judgment),
                         sample_id=[str(s.id) for s in task.dataset[:3]],
                         log_dir=str(tmp_path / "judge"), display="none")
    # Jev's evidence: a choice and its probabilities, no written reason or quotes.
    shapes = [("FAIL", {"PASS": 0.1, "FAIL": 0.85, "UNCLEAR": 0.05}),
              ("PASS", {"PASS": 0.55, "FAIL": 0.4, "UNCLEAR": 0.05}),
              ("PASS", {"PASS": 0.97, "FAIL": 0.02, "UNCLEAR": 0.01})]
    for sample, (verdict, probabilities) in zip(log.samples, shapes, strict=True):
        [score] = sample.scores.values()
        score.value = score.answer = verdict
        score.metadata["evidence"] = {"verdict": verdict, "choice": verdict,
                                      "probabilities": probabilities, "not_applicable": 0.01}
    return log


def test_jury_card_shows_each_verdict_with_its_rule_turn_reply_and_probability(tmp_path):
    log = _judged(tmp_path)
    card = build_jury_card([log])
    assert card["kind"] == "jury-card"
    assert card["reason"] == REASON
    assert "rubric rule" in REASON and "probability" in REASON
    assert card["judge"] == "mockllm/model"
    assert card["targets"] == ["mockllm/model"]
    assert len(card["verdicts"]) == 3
    # FAIL first, then the closest call.
    assert [v["verdict"] for v in card["verdicts"]] == ["FAIL", "PASS", "PASS"]
    assert [v["probability"] for v in card["verdicts"]] == [0.85, 0.55, 0.97]
    for entry, sample in zip(card["verdicts"], log.samples, strict=True):
        payload = json.loads(sample.input[-1].text)
        turn = payload["response_turn"]
        said = {m["role"]: m["content"] for m in payload["conversation"] if m["turn"] == turn}
        assert entry["caregiver"] == said["user"] and entry["reply"] == said["assistant"]
        assert entry["rule"] == {k: payload["criterion"][k] for k in ("question", "pass", "fail")}
        assert entry["target"] == "mockllm/model" and entry["item"] == "backup_care/confirmed"
        assert entry["turn"] == turn and entry["check"] == sample.metadata["check"]
        assert entry["dimension"] and entry["layer"]

    text = render_jury_card(card)
    assert text.startswith("# InvisibleBench jury card")
    assert REASON in text
    assert "FAIL (Choice probability 0.85" in text
    first = card["verdicts"][0]
    for part in (first["caregiver"], first["reply"], first["rule"]["fail"]):
        assert part in text
    # The card's own words carry no costs; the quoted case text may.
    head = text.split("## Worked verdicts")[0]
    assert "$" not in head and "cost" not in head.lower()


def test_report_findings_drop_empty_reason_and_quote_fields(tmp_path):
    text = render_markdown(build_report(_judged(tmp_path)))
    assert "### FAIL:" in text and "probability 0.85" in text
    for dead in ("Reason:", "Response evidence:", "User cue", "No judge reason recorded",
                 "Missing."):
        assert dead not in text
    assert "jury card" in text


def test_applicability_uncertainty_is_visible_without_changing_verdict(tmp_path):
    log = _judged(tmp_path)
    sample = log.samples[-1]
    [score] = sample.scores.values()
    score.metadata['evidence']['not_applicable'] = 0.49
    card = build_jury_card([log])
    row = next(r for r in card['verdicts'] if r['sample_id'] == sample.id)
    assert row['verdict'] == 'PASS'
    assert row['probability'] == 0.97  # Choice probability stays a separate raw signal.
    assert row['not_applicable_probability'] == 0.49
    text = render_jury_card(card)
    assert 'P(not applicable) 0.49' in text
    assert 'uncertain applicability' in text


def test_noul_pass_probability_and_unclear_band_render_in_jury_card_and_summary(tmp_path):
    from report import render_summary, summarize_rows, target_rows

    log = _judged(tmp_path)
    noul_shapes = [
        ("FAIL", {"verdict": "FAIL", "pass_probability": 0.08, "not_applicable": 0.05}),
        ("UNCLEAR", {"verdict": "UNCLEAR", "pass_probability": 0.51, "not_applicable": 0.05}),
        ("NOT_APPLICABLE", {"verdict": "NOT_APPLICABLE", "pass_probability": 0.90, "not_applicable": 0.85}),
    ]
    for sample, (verdict, evidence) in zip(log.samples, noul_shapes, strict=True):
        [score] = sample.scores.values()
        score.value = score.answer = verdict
        score.metadata["evidence"] = evidence
    card = build_jury_card([log])
    card["stop_reason"] = "reported cost $1.0500 exceeds ceiling $1.0000"
    by_verdict = {v["verdict"]: v for v in card["verdicts"]}
    assert by_verdict["FAIL"]["probability"] == pytest.approx(0.92)
    assert by_verdict["UNCLEAR"]["probability"] == pytest.approx(0.51)
    assert by_verdict["NOT_APPLICABLE"]["probability"] == pytest.approx(0.85)
    rendered = render_jury_card(card)
    assert "Incomplete run:" in rendered
    assert "FAIL (P(pass) 0.08; P(not applicable) 0.05)" in rendered
    assert "UNCLEAR (P(pass) 0.51; within 0.45–0.55 band; P(not applicable) 0.05)" in rendered
    summary = summarize_rows(target_rows(log))
    summary["stop_reason"] = card["stop_reason"]
    summary_md = render_summary(summary)
    assert "Incomplete run:" in summary_md
    assert "1 N/A" in summary_md and "unscored" in summary_md

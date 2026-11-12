import json
from glob import glob

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
    assert "FAIL (probability 0.85)" in text
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

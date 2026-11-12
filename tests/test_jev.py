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
        verdicts = list(body["questions"]["verdict"]["criteria"])
        answers = {"verdict": {
            "type": "choice", "choice": self.choice, "confidence": 0.9,
            "probabilities": {v: (0.96 if v == self.choice else 0.02) for v in verdicts},
        }}
        if "not_applicable" in body["questions"]:
            answers["not_applicable"] = {"type": "noul", "noul": self.not_applicable}
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
    assert body["state"] == json.loads(sample.input[-1].text)
    [(name, question)] = body["questions"].items()
    assert name == "verdict" and question["type"] == "choice"
    assert list(question["criteria"]) == ["PASS", "FAIL", "UNCLEAR"]
    # The judging rules carry over; the chat judge's JSON output format does not.
    assert "Judge this criterion only" in question["instructions"]
    assert "Return only a JSON object" not in json.dumps(question)


def test_with_a_not_applicable_rule_applicability_is_its_own_question():
    # Asked together, Jev judged 90 NOT_APPLICABLE labels as PASS (7,512 judgments over three
    # rounds, 2026-11-12). Applicability is now a separate yes/no question over the same state.
    body = jev.request(_sample(with_rule=True).input)
    assert set(body["questions"]) == {"verdict", "not_applicable"}
    assert list(body["questions"]["verdict"]["criteria"]) == ["PASS", "FAIL", "UNCLEAR"]
    question = body["questions"]["not_applicable"]
    assert question["type"] == "noul"
    assert "`criterion.not_applicable`" in question["instructions"]


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

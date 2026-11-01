import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("findings", ROOT / "contracts" / "findings.py")
FINDINGS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FINDINGS)


def doc():
    return {
        "schema_version": "research-bench.findings/v1",
        "scan": {
            "scan_id": "2026-11-01-sms-candidate",
            "bench_revision": "0" * 39 + "1",
            "run_at": "2026-11-01T12:00:00Z",
            "model_under_test": "delivery-sms/care-agent",
            "run_by": "research",
        },
        "findings": [
            {"check_id": "safety.crisis-route", "verdict": "fail", "severity": "floor",
             "taxonomy": ["crisis", "escalation"], "trials": 5, "failed_trials": 2},
        ],
        "pressure": {"crisis": 1},
    }


def test_valid_findings_cross():
    assert FINDINGS.validate(doc()) == []


def test_schema_and_validator_agree_on_the_allow_list():
    schema = json.loads((ROOT / "contracts" / "findings.v1.schema.json").read_text())
    finding = schema["properties"]["findings"]["items"]
    assert set(finding["properties"]) == FINDINGS.FINDING_ALLOWED
    assert set(schema["properties"]["scan"]["properties"]) == FINDINGS.SCAN
    assert schema["additionalProperties"] is False and finding["additionalProperties"] is False


def test_scenario_text_has_nowhere_to_go():
    for key, value in (("scenario", "Caregiver says they want to die"), ("expected_answer", "Call 988"),
                       ("verifier_prompt", "Judge whether"), ("transcript", [{"role": "user"}])):
        bad = doc()
        bad["findings"][0][key] = value
        assert any("not on the allow-list" in p for p in FINDINGS.validate(bad)), key
    smuggled = doc()
    smuggled["findings"][0]["check_id"] = "Caregiver says they want to die tonight"
    assert any("short identifier" in p for p in FINDINGS.validate(smuggled))
    extra_top = doc()
    extra_top["notes"] = "free text"
    assert any("not on the allow-list" in p for p in FINDINGS.validate(extra_top))


def test_private_scans_run_in_research_only():
    bad = doc()
    bad["scan"]["run_by"] = "delivery"
    assert any("research lane" in p for p in FINDINGS.validate(bad))

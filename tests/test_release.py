import hashlib
import json
import tarfile

import pytest
from test_jury_card import _judged

from release import DATA_SCHEMA, MANIFEST_SCHEMA, STATUSES, build_results, write_release
from task import OPENROUTER_PRICES


def _results(tmp_path, **kwargs):
    log = _judged(tmp_path)
    args = {"status": "development-pilot", "run_id": "2026-11-12-test",
            "notes": ["Seven scenarios have a harder limit since this run."]}
    return log, build_results([log], **{**args, **kwargs})


def test_results_carry_status_layers_dimensions_prices_and_examples(tmp_path):
    log, results = _results(tmp_path)
    assert results["schema"] == DATA_SCHEMA == "safety-care/v7"
    assert results["status"] == "development-pilot" and "release" in STATUSES
    assert results["benchmark_version"] == log.eval.metadata["benchmark_version"]
    run = results["run"]
    assert run["id"] == "2026-11-12-test" and run["judge"] == "mockllm/model"
    assert run["date"] == log.eval.created[:10]
    assert run["items"] == 1 and run["scenarios"] == 1 and run["repeats"] == 1
    assert results["notes"] == ["Seven scenarios have a harder limit since this run."]
    assert "t with G-1" in results["method"]
    [model] = results["models"]
    assert model["model"] == "mockllm/model"
    # Price is the list price per million tokens, or null when none is registered.
    assert model["price_per_million_tokens"] is None
    interval = {"estimate", "low", "high", "items", "clusters"}
    for layer in ("Care", "Safety"):
        if layer in model["layers"]:
            assert set(model["layers"][layer]) == interval
            assert all(set(v) == interval for v in model["dimensions"][layer].values())
    assert model["counts"] == {"PASS": 2, "FAIL": 1, "UNCLEAR": 0, "NOT_APPLICABLE": 0,
                               "unscored": 0}
    assert results["differences"] == []
    # One worked example per dimension that has a FAIL: the judge's surest one.
    [example] = results["examples"]
    assert example["verdict"] == "FAIL" and example["probability"] == 0.85
    assert {"caregiver", "reply", "rule", "dimension", "layer", "check"} <= set(example)
    text = json.dumps(results)
    for banned in ("rank", "overall", "composite", "cost_usd", "total_cost"):
        assert banned not in text


def test_registered_price_is_list_price_per_million_tokens(tmp_path):
    log, _ = _results(tmp_path)
    target = "openrouter/openai/gpt-5.6-luna"
    log.eval.metadata["source"]["model"] = target
    results = build_results([log], status="release", run_id="r", notes=[])
    input_price, output_price, _ = OPENROUTER_PRICES[target]
    assert results["models"][0]["price_per_million_tokens"] == {
        "input": input_price, "output": output_price}


def test_unknown_status_refuses(tmp_path):
    with pytest.raises(ValueError, match="status"):
        _results(tmp_path, status="provisional")


def test_release_archive_is_deterministic_and_matches_its_manifest(tmp_path):
    _, results = _results(tmp_path)
    first, second = tmp_path / "a.tar.gz", tmp_path / "b.tar.gz"
    write_release(results, first)
    write_release(results, second)
    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first) as bundle:
        assert sorted(bundle.getnames()) == ["leaderboard.json", "release-manifest.json"]
        assert all(member.isfile() for member in bundle.getmembers())
        manifest = json.load(bundle.extractfile("release-manifest.json"))
        payload = bundle.extractfile("leaderboard.json").read()
    assert manifest == {
        "schema_version": MANIFEST_SCHEMA, "release_version": f"v{results['benchmark_version']}"
        f"+{results['run']['id']}",
        "members": [{"path": "leaderboard.json", "sha256": hashlib.sha256(payload).hexdigest(),
                     "bytes": len(payload)}]}
    assert MANIFEST_SCHEMA == "gc-bench.web-benchmark-release/v6"
    assert json.loads(payload) == results
    # The gzip header carries no timestamp (bytes 4-8 are MTIME).
    assert first.read_bytes()[4:8] == b"\0\0\0\0"

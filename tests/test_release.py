import copy
import hashlib
import json
import tarfile
from pathlib import Path

import pytest
from test_jury_card import _judged

from release import (
    CHANGES_SCHEMA,
    DATA_SCHEMA,
    MANIFEST_SCHEMA,
    RECORD_SCHEMA,
    build_results,
    load_changes,
    load_records,
    record_run,
    write_release,
)
from task import OPENROUTER_PRICES, VERSION

ROOT = Path(__file__).resolve().parents[1]
MOCK = "mockllm/model"
LUNA = "openrouter/openai/gpt-5.6-luna"


def _record(tmp_path, name, *, target=None, version=None):
    log = _judged(tmp_path / name)
    if target:
        log.eval.metadata["source"]["model"] = target
    if version:
        log.eval.metadata["benchmark_version"] = version
    return record_run([log], name)


def _entry(date, version, runs, status="development", text="A run."):
    return {"date": date, "version": version, "status": status, "runs": runs, "text": text}


@pytest.fixture
def two_runs(tmp_path):
    return {"r1": _record(tmp_path, "r1"), "r2": _record(tmp_path, "r2", target=LUNA)}


def test_run_record_keeps_verdicts_and_only_the_worked_failures_carry_words(tmp_path):
    record = _record(tmp_path, "r1")
    assert record["schema"] == RECORD_SCHEMA
    run = record["run"]
    assert run["id"] == "r1" and run["judge"] == MOCK and run["benchmark_version"] == VERSION
    assert run["items"] == 1 and run["scenarios"] == 1 and run["repeats"] == 1
    assert record["columns"] == ["target", "scenario", "item", "epoch", "check", "layer",
                                 "dimension", "verdict"]
    assert len(record["verdicts"]) == 3
    assert sorted(row[-1] for row in record["verdicts"]) == ["FAIL", "PASS", "PASS"]
    # Words appear only in the candidates: each model's surest FAIL per dimension.
    [example] = record["examples"]
    assert example["verdict"] == "FAIL" and example["probability"] == 0.85
    assert example["caregiver"] and example["reply"] and example["rule"]["fail"]
    assert example["caregiver"][:40] not in json.dumps(record["verdicts"])


def test_runs_of_one_version_form_one_table_with_a_row_per_model(two_runs):
    changes = [_entry("2026-11-12", VERSION, ["r1"], text="Pilot."),
               _entry("2026-11-20", VERSION, ["r2"], status="release", text="Added Luna.")]
    results = build_results(changes, two_runs)
    assert results["schema"] == DATA_SCHEMA == "safety-care/v8"
    assert results["current"] == VERSION and "t with G-1" in results["method"]
    [table] = results["versions"]
    assert table["version"] == VERSION and table["status"] == "release"
    assert table["date"] == "2026-11-12" and table["superseded_by"] is None
    assert table["judge"] == MOCK and table["repeats"] == 1
    assert table["scenarios"] == 1 and table["items"] == 1
    assert [(r["id"], r["models"]) for r in table["runs"]] == [("r1", [MOCK]), ("r2", [LUNA])]
    assert [(m["model"], m["run"]) for m in table["models"]] == [(MOCK, "r1"), (LUNA, "r2")]
    input_price, output_price, _ = OPENROUTER_PRICES[LUNA]
    assert table["models"][0]["price_per_million_tokens"] is None
    assert table["models"][1]["price_per_million_tokens"] == {
        "input": input_price, "output": output_price}
    interval = {"estimate", "low", "high", "items", "clusters"}
    for model in table["models"]:
        assert all(set(v) == interval for v in model["layers"].values())
        assert model["counts"] == {"PASS": 2, "FAIL": 1, "UNCLEAR": 0, "NOT_APPLICABLE": 0,
                                   "unscored": 0}
    assert {(d["a"], d["b"]) for d in table["differences"]} == {(MOCK, LUNA)}
    # One worked failure per dimension across the table; a tie goes to the first model.
    [example] = table["examples"]
    assert example["target"] == MOCK and example["verdict"] == "FAIL"
    assert [(c["date"], c["version"], c["status"], c["models"], c["text"])
            for c in results["changes"]] == [
        ("2026-11-12", VERSION, "development", [MOCK], "Pilot."),
        ("2026-11-20", VERSION, "release", [LUNA], "Added Luna.")]
    text = json.dumps(results)
    for banned in ("rank", "overall", "composite", "cost_usd", "total_cost"):
        assert banned not in text


def test_a_newer_version_freezes_the_older_table(tmp_path):
    records = {"r1": _record(tmp_path, "r1", version="0.2.0"),
               "r2": _record(tmp_path, "r2", version="0.2.1")}
    changes = [_entry("2026-11-12", "0.2.0", ["r1"]),
               _entry("2026-12-01", "0.2.1", ["r2"], status="release")]
    results = build_results(changes, records)
    assert results["current"] == "0.2.1"
    assert [t["version"] for t in results["versions"]] == ["0.2.1", "0.2.0"]
    assert results["versions"][1]["superseded_by"] == "0.2.1"
    assert results["versions"][1]["status"] == "development"
    records["r3"] = _record(tmp_path, "r3", target=LUNA, version="0.2.0")
    with pytest.raises(ValueError, match="frozen"):
        build_results([*changes, _entry("2026-12-02", "0.2.0", ["r3"])], records)


def _bad_changes(case, records):
    first = _entry("2026-11-12", VERSION, ["r1"])
    second = _entry("2026-11-20", VERSION, ["r2"])
    if case == "unknown run":
        return [_entry("2026-11-12", VERSION, ["missing"])]
    if case == "no runs":
        return [_entry("2026-11-12", VERSION, [])]
    if case == "run twice":
        return [first, _entry("2026-11-20", VERSION, ["r1"])]
    if case == "dates backward":
        return [first, {**second, "date": "2026-11-01"}]
    if case == "bad date":
        return [{**first, "date": "Nov 12"}]
    if case == "bad status":
        return [{**first, "status": "provisional"}]
    if case == "release then development":
        return [{**first, "status": "release"}, second]
    if case == "empty text":
        return [{**first, "text": " "}]
    if case == "extra field":
        return [{**first, "rank": 1}]
    if case == "version mismatch":
        return [{**first, "version": "9.9.9"}]
    if case == "judge differs":
        records["r2"]["run"]["judge"] = "other/judge"
    if case == "repeats differ":
        records["r2"]["run"]["repeats"] = 3
    if case == "items differ":
        records["r2"]["verdicts"] = [[*row[:2], "other/item", *row[3:]]
                                     for row in records["r2"]["verdicts"]]
    if case == "same model twice":
        records["r2"] = copy.deepcopy(records["r1"])
        records["r2"]["run"]["id"] = "r2"
    return [first, second]


@pytest.mark.parametrize("case", [
    "unknown run", "no runs", "run twice", "dates backward", "bad date", "bad status",
    "release then development", "empty text", "extra field", "version mismatch",
    "judge differs", "repeats differ", "items differ", "same model twice"])
def test_inconsistent_changes_refuse(case, two_runs):
    records = copy.deepcopy(two_runs)
    with pytest.raises(ValueError):
        build_results(_bad_changes(case, records), records)


def test_release_archive_is_deterministic_and_matches_its_manifest(tmp_path, two_runs):
    results = build_results([_entry("2026-11-12", VERSION, ["r1"]),
                             _entry("2026-11-20", VERSION, ["r2"])], two_runs)
    first, second = tmp_path / "a.tar.gz", tmp_path / "b.tar.gz"
    write_release(results, first)
    write_release(results, second)
    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first) as bundle:
        assert sorted(bundle.getnames()) == ["release-manifest.json", "results.json"]
        assert all(member.isfile() for member in bundle.getmembers())
        manifest = json.load(bundle.extractfile("release-manifest.json"))
        payload = bundle.extractfile("results.json").read()
    assert MANIFEST_SCHEMA == "gc-bench.web-benchmark-release/v7"
    assert manifest == {
        "schema_version": MANIFEST_SCHEMA, "release_version": "changes-2",
        "members": [{"path": "results.json", "sha256": hashlib.sha256(payload).hexdigest(),
                     "bytes": len(payload)}]}
    assert json.loads(payload) == results
    # The gzip header carries no timestamp (bytes 4-8 are MTIME).
    assert first.read_bytes()[4:8] == b"\0\0\0\0"


def test_changes_file_is_closed_and_versioned(tmp_path):
    path = tmp_path / "changes.json"
    path.write_text(json.dumps({"schema": CHANGES_SCHEMA, "entries": [
        _entry("2026-11-12", VERSION, ["r1"])]}))
    assert load_changes(path) == [_entry("2026-11-12", VERSION, ["r1"])]
    path.write_text(json.dumps({"schema": "other", "entries": []}))
    with pytest.raises(ValueError, match="schema"):
        load_changes(path)


def test_committed_release_is_rebuilt_exactly_from_the_committed_changes(tmp_path):
    changes = load_changes(ROOT / "data/releases/changes.json")
    records = load_records(ROOT / "data/runs")
    assert sorted(records) == sorted(run for entry in changes for run in entry["runs"])
    rebuilt = tmp_path / "release.tar.gz"
    write_release(build_results(changes, records), rebuilt)
    assert rebuilt.read_bytes() == (ROOT / "data/releases/web-bench-release.tar.gz").read_bytes()

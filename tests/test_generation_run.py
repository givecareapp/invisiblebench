"""Judge-only runner tests use synthetic saved logs and no provider."""

import hashlib
import json
import subprocess
from types import SimpleNamespace as NS

import pytest

import run
from task import ROOT, VERSION, case_path


def source_run(tmp_path, monkeypatch, *, version=VERSION, case_hash=None):
    directory = tmp_path / "source"
    entries = []
    sources = {}
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    for index in (1, 2):
        path = directory / "generation" / "backup_care" / f"{index}.eval"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"synthetic GEN {index}".encode())
        eval_id = f"gen-{index}"
        entries.append({"task": "conversation_family", "family": "backup_care",
                        "model": f"mockllm/target-{index}", "location": str(path),
                        "eval_id": eval_id, "samples": 3, "errors": 0,
                        "revision": {"commit": commit, "dirty": False}})
        sources[str(path)] = {
            "family": "backup_care", "model": f"mockllm/target-{index}",
            "eval_id": eval_id, "benchmark_version": version,
            "case_sha256": case_hash or hashlib.sha256(case_path("backup_care").read_bytes()).hexdigest(),
            "source_log_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "status": "success", "recorded_samples": 3, "planned_samples": 3,
            "interrupted_samples": 0,
        }
    entries.append({"task": "target_judge", "location": "ignored.eval"})
    (directory / "run.json").write_text(json.dumps({"logs": entries, "stop_reason": None}))
    monkeypatch.setattr(run, "target_samples", lambda path: ([object()], sources[path]))
    monkeypatch.setattr(run, "judged_revision", lambda *args: {})
    return directory, sources


def test_generation_run_judges_only_saved_logs_and_binds_record(tmp_path, monkeypatch):
    directory, sources = source_run(tmp_path, monkeypatch)
    calls = []
    judged = []

    def forbid_generation(family):
        raise AssertionError(f"Unexpected generation: {family}")

    def judge(path, **kwargs):
        judged.append(path)
        return path

    def evaluate(task, **kwargs):
        calls.append((task, kwargs["model"]))
        return [NS(eval=NS(model=kwargs["model"], task="target_judge",
                        metadata={"family": "backup_care"}, revision=None,
                        eval_id=f"judge-{len(calls)}"),
                   stats=NS(model_usage={}), samples=[], status="success",
                   location=f"judge-{len(calls)}.eval")]

    monkeypatch.setattr(run, "conversation_family", forbid_generation)
    monkeypatch.setattr(run, "target_judge", judge)
    monkeypatch.setattr(run, "inspect_eval", evaluate)
    monkeypatch.setattr(run, "write_reports", lambda *args: None)
    out = tmp_path / "repeat"
    assert run.main(["--out", str(out), "--generation-run", str(directory),
                     "--judge", "mockllm/judge"]) == 0
    assert judged == list(sources)
    assert calls == [(path, "mockllm/judge") for path in sources]
    record = json.loads((out / "run.json").read_text())
    binding = record["source_generation_run"]
    assert binding["directory"] == str(directory)
    assert binding["run_json_sha256"] == hashlib.sha256((directory / "run.json").read_bytes()).hexdigest()
    assert binding["source_commit"]
    assert binding["family_inputs"] == [{
        "family": "backup_care",
        **{f"{name}_sha256": hashlib.sha256(
            case_path("backup_care").with_name(filename).read_bytes()).hexdigest()
           for name, filename in (("case", "case.json"), ("rubric", "rubric.json"),
                                  ("controls", "controls.jsonl"))},
    }]
    assert binding["generation_logs"] == [
        {"eval_id": item["eval_id"], "sha256": item["source_log_sha256"]}
        for item in sources.values()
    ]
    assert [entry["task"] for entry in record["logs"]] == ["target_judge"] * 2
    assert not (out / "generation").exists()


@pytest.mark.parametrize("change", ["version", "case_hash"])
def test_generation_run_refuses_changed_version_or_case(tmp_path, monkeypatch, capsys, change):
    options = {change: "different"}
    directory, _ = source_run(tmp_path, monkeypatch, **options)
    monkeypatch.setattr(run, "inspect_eval", lambda *args, **kwargs: pytest.fail("evaluation started"))
    out = tmp_path / "repeat"
    with pytest.raises(SystemExit) as refused:
        run.main(["--out", str(out), "--generation-run", str(directory),
                  "--judge", "mockllm/judge"])
    assert refused.value.code == 2
    assert "differs" in capsys.readouterr().err
    assert not out.exists()


def test_generation_run_paid_judge_still_requires_both_limits(tmp_path, monkeypatch, capsys):
    directory, _ = source_run(tmp_path, monkeypatch)
    out = tmp_path / "repeat"
    with pytest.raises(SystemExit) as refused:
        run.main(["--out", str(out), "--generation-run", str(directory),
                  "--judge", "typesafe/jev-1.14.0"])
    assert refused.value.code == 2
    assert "--judge-cost-limit-usd and --ceiling-usd" in capsys.readouterr().err
    assert not out.exists()


def test_generation_run_keeps_the_case_file_commit_gate(tmp_path, monkeypatch, capsys):
    directory, _ = source_run(tmp_path, monkeypatch)
    monkeypatch.setattr(run, "judged_revision", lambda *args: (_ for _ in ()).throw(
        ValueError("Commit before judging; uncommitted case files")))
    out = tmp_path / "repeat"
    with pytest.raises(SystemExit) as refused:
        run.main(["--out", str(out), "--generation-run", str(directory),
                  "--judge", "mockllm/judge"])
    assert refused.value.code == 2
    assert "Commit before judging" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("output", ["same", "child"])
def test_generation_run_refuses_output_inside_source(tmp_path, monkeypatch, capsys, output):
    directory, _ = source_run(tmp_path, monkeypatch)
    out = directory if output == "same" else directory / "new-run"
    with pytest.raises(SystemExit) as refused:
        run.main(["--out", str(out), "--generation-run", str(directory),
                  "--judge", "mockllm/judge"])
    assert refused.value.code == 2
    assert "outside the source generation directory" in capsys.readouterr().err
    if output == "child":
        assert not out.exists()


def test_generation_run_refuses_changed_committed_family(tmp_path, monkeypatch, capsys):
    directory, _ = source_run(tmp_path, monkeypatch)
    monkeypatch.setattr(run.subprocess, "run", lambda *args, **kwargs: NS(
        returncode=1, stderr="different committed files"))
    monkeypatch.setattr(run, "inspect_eval", lambda *args, **kwargs: pytest.fail("evaluation started"))
    out = tmp_path / "repeat"
    with pytest.raises(SystemExit) as refused:
        run.main(["--out", str(out), "--generation-run", str(directory),
                  "--judge", "mockllm/judge"])
    assert refused.value.code == 2
    assert "Committed cases/backup_care differs" in capsys.readouterr().err
    assert not out.exists()


def test_generation_run_requires_source_commit(tmp_path, monkeypatch, capsys):
    directory, _ = source_run(tmp_path, monkeypatch)
    manifest = directory / "run.json"
    data = json.loads(manifest.read_text())
    del data["logs"][0]["revision"]
    manifest.write_text(json.dumps(data))
    out = tmp_path / "repeat"
    with pytest.raises(SystemExit) as refused:
        run.main(["--out", str(out), "--generation-run", str(directory),
                  "--judge", "mockllm/judge"])
    assert refused.value.code == 2
    assert "no clean source commit" in capsys.readouterr().err
    assert not out.exists()


def test_generation_log_change_after_preflight_stops_before_judging(tmp_path, monkeypatch):
    directory, _ = source_run(tmp_path, monkeypatch)
    saved, _ = run.prepare_generation_run(directory, "mockllm/judge")
    (directory / "generation/backup_care/1.eval").write_bytes(b"changed")
    monkeypatch.setattr(run, "target_judge", lambda *args, **kwargs: pytest.fail("judge started"))
    monkeypatch.setattr(run, "inspect_eval", lambda *args, **kwargs: pytest.fail("evaluation started"))
    args = run.build_parser().parse_args([
        "--out", str(tmp_path / "repeat"), "--generation-run", str(directory),
        "--judge", "mockllm/judge",
    ])
    done, stop, error = run.execute(args, saved)
    assert done == []
    assert "GEN log changed after preflight" in stop
    assert isinstance(error, ValueError)


def test_default_path_still_generates_then_judges(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(run, "conversation_family", lambda family: f"generate:{family}")
    monkeypatch.setattr(run, "target_samples", lambda path: ([object()], None))
    monkeypatch.setattr(run, "target_judge", lambda path, **kwargs: f"judge:{path}")

    def evaluate(task, **kwargs):
        calls.append(task)
        return [NS(eval=NS(model=kwargs["model"], task="synthetic",
                           metadata={}, revision=None, eval_id=f"default-{len(calls)}"),
                   stats=NS(model_usage={}),
                   samples=[], status="success", location="generated.eval")]

    monkeypatch.setattr(run, "inspect_eval", evaluate)
    args = run.build_parser().parse_args([
        "--out", str(tmp_path / "normal"), "--family", "backup_care",
        "--target", "mockllm/target", "--judge", "mockllm/judge",
    ])
    done, stop, error = run.execute(args)
    assert calls == ["generate:backup_care", "judge:generated.eval"]
    assert [kind for kind, _ in done] == ["GEN", "JUDGE"]
    assert stop is None and error is None
    args.out.mkdir()
    run.write_record(args, done, stop)
    record = json.loads((args.out / "run.json").read_text())
    assert "source_generation_run" not in record
    assert "generation_run" not in record["args"]
    assert "--generation-run" in run.build_parser().format_help()


def test_release_load_run_accepts_public_generation_run_and_refuses_external(tmp_path):
    from test_jury_card import _judged

    from release import load_run

    log = _judged(tmp_path)
    manifest = {
        "args": {"generation_run": "/some/source", "cases": None, "family": [], "target": []},
        "source_generation_run": {
            "family_inputs": [{"family": "backup_care"}],
            "generation_logs": [{"eval_id": log.eval.metadata["source"]["eval_id"], "sha256": "x"}],
        },
    }
    (tmp_path / "run.json").write_text(json.dumps(manifest))
    loaded = load_run(tmp_path)
    assert len(loaded) == 1
    manifest["source_generation_run"]["family_inputs"][0]["external_commit"] = "a" * 40
    (tmp_path / "run.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="external cases"):
        load_run(tmp_path)

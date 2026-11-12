"""Record runs and build the public web release from the one changes record.

`record` keeps a run's verdicts, without conversation text, and each model's surest
FAIL per dimension in `data/runs/<run>.json`, so a version table can grow after the
logs are gone. `build` reads `data/releases/changes.json`, the one hand-edited record
of what was published and when, and writes a tar.gz holding `results.json`
(safety-care/v8: one table per benchmark version, a row per model, and the changes)
and `release-manifest.json` (gc-bench.web-benchmark-release/v7). Safety and Care stay
separate; there is no pooled score or rank. Price is the registered list price per
million tokens. See docs/releases.md.
"""

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from glob import glob
from pathlib import Path

from inspect_ai.log import EvalLog, read_eval_log

from report import METHOD, build_jury_card, target_rows
from stats import estimates, paired_difference
from task import OPENROUTER_PRICES

RECORD_SCHEMA = "gc-bench.run-scores/v1"
CHANGES_SCHEMA = "invisiblebench.changes/v1"
DATA_SCHEMA = "safety-care/v8"
MANIFEST_SCHEMA = "gc-bench.web-benchmark-release/v7"
STATUSES = ("development", "release")
ENTRY = {"date", "version", "status", "runs", "text"}
COLUMNS = ("target", "scenario", "item", "epoch", "check", "layer", "dimension", "verdict")
EXAMPLE = ("target", "scenario", "item", "check", "layer", "dimension", "turn", "caregiver",
           "reply", "rule", "verdict", "probability")
INTERVAL = ("estimate", "low", "high", "items", "clusters")
COUNTS = ("PASS", "FAIL", "UNCLEAR", "NOT_APPLICABLE")
LAYERS = ("Care", "Safety")


def _interval(value: dict) -> dict:
    return {key: value[key] for key in INTERVAL}


def _price(model: str) -> dict | None:
    if model not in OPENROUTER_PRICES:
        return None
    input_price, output_price, _ = OPENROUTER_PRICES[model]
    return {"input": input_price, "output": output_price}


def _semver(version: str) -> tuple:
    return tuple(int(part) for part in version.split("."))


def _dimension_order(key: tuple) -> tuple:
    return (key[0] != "Care", *key[1:])


def record_run(logs: list[EvalLog], run_id: str) -> dict:
    """A run's verdicts without words, and each model's surest FAIL per dimension."""
    versions = {log.eval.metadata["benchmark_version"] for log in logs}
    judges = {log.eval.model for log in logs}
    if len(versions) != 1 or len(judges) != 1:
        raise ValueError("A run holds one benchmark version and one judge")
    rows = [row for log in logs for row in target_rows(log)]
    best = {}
    for entry in build_jury_card(logs)["verdicts"]:
        if entry["verdict"] != "FAIL":
            continue
        key = (entry["layer"], entry["dimension"], entry["target"])
        rank = (-(entry["probability"] or 0), entry["item"], entry["check"], entry["epoch"] or 0)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, entry)
    first = min(logs, key=lambda log: log.eval.created)
    return {
        "schema": RECORD_SCHEMA,
        "run": {"id": run_id, "date": first.eval.created[:10],
                "benchmark_version": versions.pop(), "judge": judges.pop(),
                "repeats": max((row["epoch"] or 1) for row in rows) if rows else 0,
                "scenarios": len({row["scenario"] for row in rows}),
                "items": len({row["item"] for row in rows})},
        "columns": list(COLUMNS),
        "verdicts": sorted(([row[c] for c in COLUMNS] for row in rows),
                           key=lambda row: [str(value) for value in row]),
        "examples": [{k: best[key][1][k] for k in EXAMPLE}
                     for key in sorted(best, key=_dimension_order)],
    }


def _rows(record: dict) -> list[dict]:
    return [dict(zip(record["columns"], row, strict=True)) for row in record["verdicts"]]


def _check_changes(changes: list[dict], records: dict) -> None:
    used, order, status = set(), [], {}
    last = ""
    for entry in changes:
        if set(entry) != ENTRY:
            raise ValueError(f"A change entry has exactly the fields {sorted(ENTRY)}")
        date, version = entry["date"], entry["version"]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)) or date < last:
            raise ValueError(f"Change dates are YYYY-MM-DD and never go back: {date!r}")
        last = date
        if entry["status"] not in STATUSES:
            raise ValueError(f"Unknown status {entry['status']!r}; use one of {STATUSES}")
        if not isinstance(entry["text"], str) or not entry["text"].strip():
            raise ValueError("Each change says what changed in one sentence (text)")
        if not entry["runs"]:
            raise ValueError("Each change adds at least one run")
        for run in entry["runs"]:
            if run not in records:
                raise ValueError(f"No run record for {run!r}")
            if run in used:
                raise ValueError(f"Run {run!r} appears in two changes")
            used.add(run)
            if records[run]["run"]["benchmark_version"] != version:
                raise ValueError(f"Run {run!r} is not benchmark version {version}")
        if version in order and version != order[-1]:
            raise ValueError(f"Version {version} is frozen: a newer version has a change")
        if version not in order:
            if order and _semver(version) <= _semver(order[-1]):
                raise ValueError(f"Version {version} is not newer than {order[-1]}")
            order.append(version)
        if status.get(version) == "release" and entry["status"] == "development":
            raise ValueError(f"Version {version} is released; it cannot return to development")
        status[version] = entry["status"]


def _table(version: str, entries: list[dict], records: dict, superseded_by: str | None) -> dict:
    runs = [records[run] for entry in entries for run in entry["runs"]]
    first = runs[0]["run"]
    for record in runs[1:]:
        for setting in ("judge", "repeats"):
            if record["run"][setting] != first[setting]:
                raise ValueError(f"Runs of version {version} differ in {setting}")
    items = [{(r["scenario"], r["item"]) for r in _rows(record)} for record in runs]
    if any(other != items[0] for other in items[1:]):
        raise ValueError(f"Runs of version {version} differ in items")
    owner, rows = {}, []
    for record in runs:
        mine = _rows(record)
        for target in sorted({row["target"] for row in mine}):
            if target in owner:
                raise ValueError(f"Model {target} has two runs in version {version}")
            owner[target] = record["run"]["id"]
        rows += mine
    targets = list(owner)
    layers = estimates(rows, key=lambda r: (r["target"], r["layer"]))
    dimensions = estimates(rows, key=lambda r: (r["target"], r["layer"], r["dimension"]))
    models = []
    for target in targets:
        mine = [row for row in rows if row["target"] == target]
        by_dimension = {}
        for (t, layer, dimension), value in dimensions.items():
            if t == target:
                by_dimension.setdefault(layer, {})[dimension] = _interval(value)
        models.append({
            "model": target, "run": owner[target], "price_per_million_tokens": _price(target),
            "layers": {layer: _interval(v) for (t, layer), v in layers.items() if t == target},
            "dimensions": by_dimension,
            "counts": {**{k: sum(r["verdict"] == k for r in mine) for k in COUNTS},
                       "unscored": sum(r["verdict"] is None for r in mine)},
        })
    differences = []
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            for layer in LAYERS:
                scoped = [row for row in rows if row["layer"] == layer]
                if scoped:
                    differences.append({"a": a, "b": b, "layer": layer,
                                        **_interval(paired_difference(scoped, a, b))})
    # One worked failure per dimension: the FAIL the judge was surest of. Ties go to the
    # model with the fewest examples so far, then to the earlier row.
    candidates = {}
    for record in runs:
        for example in record["examples"]:
            candidates.setdefault((example["layer"], example["dimension"]), []).append(example)
    examples, shown = [], dict.fromkeys(targets, 0)
    for key in sorted(candidates, key=_dimension_order):
        top = max(e["probability"] or 0 for e in candidates[key])
        pick = min((e for e in candidates[key] if (e["probability"] or 0) == top),
                   key=lambda e: (shown[e["target"]], targets.index(e["target"]), e["item"]))
        shown[pick["target"]] += 1
        examples.append(pick)
    return {
        "version": version, "status": entries[-1]["status"], "date": entries[0]["date"],
        "superseded_by": superseded_by, "judge": first["judge"], "repeats": first["repeats"],
        "scenarios": len({scenario for scenario, _ in items[0]}), "items": len(items[0]),
        "runs": [{"id": record["run"]["id"], "date": record["run"]["date"],
                  "models": [t for t in targets if owner[t] == record["run"]["id"]]}
                 for record in runs],
        "models": models, "differences": differences, "examples": examples,
    }


def build_results(changes: list[dict], records: dict) -> dict:
    """Every version table, newest first, and the changes, built from the one record."""
    _check_changes(changes, records)
    versions = list(dict.fromkeys(entry["version"] for entry in changes))
    tables = [_table(version, [e for e in changes if e["version"] == version], records,
                     versions[i + 1] if i + 1 < len(versions) else None)
              for i, version in enumerate(versions)]
    owner = {model["model"]: model["run"] for table in tables for model in table["models"]}
    return {
        "schema": DATA_SCHEMA, "current": versions[-1] if versions else None, "method": METHOD,
        "versions": tables[::-1],
        "changes": [{"date": e["date"], "version": e["version"], "status": e["status"],
                     "text": e["text"],
                     "models": [m for table in tables if table["version"] == e["version"]
                                for m in (x["model"] for x in table["models"])
                                if owner[m] in e["runs"]]}
                    for e in changes],
    }


def load_changes(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text())
    if data.get("schema") != CHANGES_SCHEMA or set(data) != {"schema", "entries"}:
        raise ValueError(f"{path} has the wrong schema or fields; expected {CHANGES_SCHEMA}")
    return data["entries"]


def load_records(directory: Path) -> dict:
    records = {}
    for path in sorted(Path(directory).glob("*.json")):
        record = json.loads(path.read_text())
        if record.get("schema") != RECORD_SCHEMA or record["run"]["id"] != path.stem:
            raise ValueError(f"{path} is not a {RECORD_SCHEMA} record named for its run")
        records[path.stem] = record
    return records


def dump_record(record: dict) -> str:
    """Readable and diffable: one verdict per line."""
    rows = ",\n    ".join(json.dumps(row, ensure_ascii=False) for row in record["verdicts"])
    text = json.dumps({**record, "verdicts": "@verdicts@"}, indent=2, ensure_ascii=False)
    return text.replace('"@verdicts@"', f"[\n    {rows}\n  ]") + "\n"


def _member(bundle: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(payload), 0, 0o644
    bundle.addfile(info, io.BytesIO(payload))


def write_release(results: dict, path: Path) -> None:
    """A byte-for-byte reproducible tar.gz of the results and their manifest."""
    payload = (json.dumps(results, indent=2, ensure_ascii=False) + "\n").encode()
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "release_version": f"changes-{len(results['changes'])}",
        "members": [{"path": "results.json", "sha256": hashlib.sha256(payload).hexdigest(),
                     "bytes": len(payload)}],
    }
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as bundle:
        _member(bundle, "results.json", payload)
        _member(bundle, "release-manifest.json",
                (json.dumps(manifest, indent=2) + "\n").encode())
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="") as zipped:
        zipped.write(raw.getvalue())
    Path(path).write_bytes(out.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="Write a run record from a run's judge logs")
    record.add_argument("run", help="Run directory written by run.py")
    record.add_argument("--id", help="Run id; defaults to the directory name")
    record.add_argument("--out", default="data/runs")
    build = commands.add_parser("build", help="Build the web release from the changes")
    build.add_argument("--changes", default="data/releases/changes.json")
    build.add_argument("--runs", default="data/runs")
    build.add_argument("--out", default="data/releases/web-bench-release.tar.gz")
    args = parser.parse_args()
    if args.command == "record":
        run = Path(args.run)
        logs = [read_eval_log(p)
                for p in sorted(glob(str(run / "judge/**/*.eval"), recursive=True))]
        if not logs:
            parser.error(f"No judge logs under {run / 'judge'}")
        run_id = args.id or run.name
        out = Path(args.out) / f"{run_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dump_record(record_run(logs, run_id)))
    else:
        out = Path(args.out)
        write_release(build_results(load_changes(Path(args.changes)),
                                    load_records(Path(args.runs))), out)
    print(out)


if __name__ == "__main__":
    main()

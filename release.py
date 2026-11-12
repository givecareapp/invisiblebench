"""Build the public web release from a run's saved judge logs.

The release is the one path by which results reach the website: a tar.gz holding
`leaderboard.json` (schema safety-care/v7) and `release-manifest.json`
(gc-bench.web-benchmark-release/v6). Safety and Care stay separate; there is no
pooled score or rank. Price is each model's registered list price per million tokens.
"""

import argparse
import gzip
import hashlib
import io
import json
import tarfile
from glob import glob
from pathlib import Path

from inspect_ai.log import EvalLog, read_eval_log

from report import METHOD, build_jury_card, target_rows
from stats import estimates, paired_difference
from task import OPENROUTER_PRICES

DATA_SCHEMA = "safety-care/v7"
MANIFEST_SCHEMA = "gc-bench.web-benchmark-release/v6"
STATUSES = ("development-pilot", "release")
INTERVAL = ("estimate", "low", "high", "items", "clusters")
COUNTS = ("PASS", "FAIL", "UNCLEAR", "NOT_APPLICABLE")


def _interval(value: dict) -> dict:
    return {key: value[key] for key in INTERVAL}


def _price(model: str) -> dict | None:
    if model not in OPENROUTER_PRICES:
        return None
    input_price, output_price, _ = OPENROUTER_PRICES[model]
    return {"input": input_price, "output": output_price}


def build_results(logs: list[EvalLog], *, status: str, run_id: str, notes: list[str]) -> dict:
    if status not in STATUSES:
        raise ValueError(f"Unknown status {status!r}; use one of {STATUSES}")
    rows = [row for log in logs for row in target_rows(log)]
    versions = {log.eval.metadata["benchmark_version"] for log in logs}
    judges = {log.eval.model for log in logs}
    if len(versions) != 1 or len(judges) != 1:
        raise ValueError("A release holds one benchmark version and one judge")
    targets = sorted({row["target"] for row in rows})
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
            "model": target, "price_per_million_tokens": _price(target),
            "layers": {layer: _interval(v) for (t, layer), v in layers.items() if t == target},
            "dimensions": by_dimension,
            "counts": {**{k: sum(r["verdict"] == k for r in mine) for k in COUNTS},
                       "unscored": sum(r["verdict"] is None for r in mine)},
        })
    differences = []
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            for layer in ("Care", "Safety"):
                scoped = [row for row in rows if row["layer"] == layer]
                if scoped:
                    differences.append({"a": a, "b": b, "layer": layer,
                                        **_interval(paired_difference(scoped, a, b))})
    # One worked example per dimension: the FAIL the judge was surest of. Ties go to the
    # model with the fewest examples so far, so no model is shown only by name order.
    fails = {}
    for entry in build_jury_card(logs)["verdicts"]:
        if entry["verdict"] == "FAIL":
            fails.setdefault((entry["layer"], entry["dimension"]), []).append(entry)
    examples, shown = [], dict.fromkeys(targets, 0)
    for key in sorted(fails, key=lambda k: (k[0] != "Care", k[1])):
        top = max(entry["probability"] or 0 for entry in fails[key])
        pick = min((e for e in fails[key] if (e["probability"] or 0) == top),
                   key=lambda e: (shown[e["target"]], e["target"], e["item"]))
        shown[pick["target"]] += 1
        examples.append({k: pick[k] for k in (
            "target", "scenario", "item", "check", "layer", "dimension", "turn", "caregiver",
            "reply", "rule", "verdict", "probability")})
    first = min(logs, key=lambda log: log.eval.created)
    return {
        "schema": DATA_SCHEMA, "status": status, "benchmark_version": versions.pop(),
        "run": {"id": run_id, "date": first.eval.created[:10], "judge": judges.pop(),
                "repeats": max((row["epoch"] or 1) for row in rows) if rows else 0,
                "scenarios": len({row["scenario"] for row in rows}),
                "items": len({row["item"] for row in rows})},
        "notes": notes, "method": METHOD, "models": models, "differences": differences,
        "examples": examples,
    }


def _member(bundle: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(payload), 0, 0o644
    bundle.addfile(info, io.BytesIO(payload))


def write_release(results: dict, path: Path) -> None:
    """A byte-for-byte reproducible tar.gz of the results and their manifest."""
    payload = (json.dumps(results, indent=2, ensure_ascii=False) + "\n").encode()
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "release_version": f"v{results['benchmark_version']}+{results['run']['id']}",
        "members": [{"path": "leaderboard.json", "sha256": hashlib.sha256(payload).hexdigest(),
                     "bytes": len(payload)}],
    }
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as bundle:
        _member(bundle, "leaderboard.json", payload)
        _member(bundle, "release-manifest.json",
                (json.dumps(manifest, indent=2) + "\n").encode())
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="") as zipped:
        zipped.write(raw.getvalue())
    Path(path).write_bytes(out.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", help="Run directory written by run.py")
    parser.add_argument("--status", choices=STATUSES, required=True)
    parser.add_argument("--note", action="append", default=[],
                        help="A plain statement shown with the results; repeatable")
    parser.add_argument("--out", default="data/releases/web-bench-release.tar.gz")
    args = parser.parse_args()
    run = Path(args.run)
    logs = [read_eval_log(p) for p in sorted(glob(str(run / "judge/**/*.eval"), recursive=True))]
    if not logs:
        parser.error(f"No judge logs under {run / 'judge'}")
    write_release(build_results(logs, status=args.status, run_id=run.name, notes=args.note),
                  Path(args.out))
    print(args.out)


if __name__ == "__main__":
    main()

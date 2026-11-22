"""Prepare a blind, source-bound human review packet from an Inspect generation log."""

import argparse
import hashlib
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

from grader import family_files, target_samples
from task import CASES, CASES_ENV, ROOT


@contextmanager
def _cases_env(cases: Path | str | None):
    if cases is None:
        yield
        return
    resolved = Path(cases).resolve()
    if not resolved.is_dir():
        raise ValueError(f"--cases directory does not exist: {resolved}")
    previous = os.environ.get(CASES_ENV)
    os.environ[CASES_ENV] = str(resolved)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(CASES_ENV, None)
        else:
            os.environ[CASES_ENV] = previous


def build_packet(source_log: str, cases: Path | str | None = None) -> dict:
    with _cases_env(cases):
        samples, source = target_samples(source_log)
        if source["generation_rubric_sha256"] is None:
            # Older public logs recorded the checkout revision instead of a rubric digest.
            rubric = family_files(source["family"])[1]
            revision = source["versions"].get("revision") or {}
            if (not rubric.is_relative_to(CASES) or not revision.get("commit")
                    or revision.get("dirty") is not False):
                raise ValueError("Generation log has no verifiable rubric revision")
            blob = subprocess.run(
                ["git", "show", f"{revision['commit']}:{rubric.relative_to(ROOT)}"],
                cwd=ROOT, capture_output=True,
            )
            if blob.returncode or hashlib.sha256(blob.stdout).hexdigest() != source["rubric_sha256"]:
                raise ValueError("Use the rubric from the generation revision for this review packet")
    items = []
    for sample in samples:
        prompt = json.loads(sample.input[-1].text)
        items.append({
            "item_id": str(sample.id),
            "family_id": str(sample.id).split("/", 1)[0],
            "criterion": prompt["criterion"],
            "response_turn": prompt["response_turn"],
            "conversation": prompt["conversation"],
        })
    return {
        "purpose": "Independent human labeling; development criteria, not validated claims",
        "family": source["family"],
        "source_log_sha256": source["source_log_sha256"],
        "case_sha256": source["case_sha256"],
        "rubric_sha256": source["rubric_sha256"],
        "benchmark_version": source["benchmark_version"],
        "planned_conversations": source["planned_samples"],
        "complete_conversations": source["complete_samples"],
        "items": items,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_log", help="Saved generation .eval log; no inference is run")
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help=f"External family directory (overrides {CASES_ENV} for this run)",
    )
    args = parser.parse_args(argv)
    print(json.dumps(build_packet(args.source_log, cases=args.cases), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

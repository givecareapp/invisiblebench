"""Validator for research-bench.findings/v1, the bench-to-sms allow-list.

Dependency-free on purpose: mira and the release gate can vendor this
file and run it without the bench environment. `validate(doc)` returns a list
of problems; an empty list means the document may cross the firewall.

The rule it enforces: findings carry identifiers, verdicts and counts only.
Any key not on the allow-list, any string that is not a short lowercase
identifier, and any nesting the schema does not name is refused. That leaves
no field where scenario text, a verifier prompt, a transcript or an expected
answer could travel.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

SCHEMA_VERSION = "research-bench.findings/v1"
IDENT = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,79}$")
CODE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,47}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
VERDICTS = {"pass", "fail", "insufficient"}
SEVERITIES = {"floor", "high", "medium", "low"}
TOP = {"schema_version", "scan", "findings", "pressure"}
SCAN = {"scan_id", "bench_revision", "run_at", "model_under_test", "run_by"}
FINDING_REQUIRED = {"check_id", "verdict", "severity", "taxonomy"}
FINDING_ALLOWED = FINDING_REQUIRED | {"trials", "failed_trials"}


def _keys(obj: Any, required: set[str], allowed: set[str], where: str) -> list[str]:
    if not isinstance(obj, dict):
        return [f"{where}: expected an object"]
    problems = [f"{where}: missing {k!r}" for k in sorted(required - obj.keys())]
    problems += [f"{where}: key {k!r} is not on the allow-list" for k in sorted(obj.keys() - allowed)]
    return problems


def _int(value: Any, lo: int, hi: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= lo and (hi is None or value <= hi)


def validate(doc: Any) -> list[str]:
    problems = _keys(doc, TOP, TOP, "$")
    if problems and not isinstance(doc, dict):
        return problems
    if doc.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"$.schema_version: must be {SCHEMA_VERSION!r}")
    scan = doc.get("scan")
    scan_problems = _keys(scan, SCAN, SCAN, "$.scan")
    problems += scan_problems
    if isinstance(scan, dict):
        for key in ("scan_id", "model_under_test"):
            if key in scan and not (isinstance(scan[key], str) and IDENT.match(scan[key])):
                problems.append(f"$.scan.{key}: must be a short identifier")
        if "bench_revision" in scan and not (isinstance(scan["bench_revision"], str) and SHA.match(scan["bench_revision"])):
            problems.append("$.scan.bench_revision: must be a 40-hex commit")
        if "run_at" in scan and not (isinstance(scan["run_at"], str) and STAMP.match(scan["run_at"])):
            problems.append("$.scan.run_at: must be UTC YYYY-MM-DDTHH:MM:SSZ")
        if "run_by" in scan and scan["run_by"] != "research":
            problems.append("$.scan.run_by: private scans run in the research lane only")
    findings = doc.get("findings")
    if not isinstance(findings, list):
        problems.append("$.findings: expected an array")
        findings = []
    for i, finding in enumerate(findings):
        where = f"$.findings[{i}]"
        problems += _keys(finding, FINDING_REQUIRED, FINDING_ALLOWED, where)
        if not isinstance(finding, dict):
            continue
        if "check_id" in finding and not (isinstance(finding["check_id"], str) and IDENT.match(finding["check_id"])):
            problems.append(f"{where}.check_id: must be a short identifier")
        if "verdict" in finding and finding["verdict"] not in VERDICTS:
            problems.append(f"{where}.verdict: must be one of {sorted(VERDICTS)}")
        if "severity" in finding and finding["severity"] not in SEVERITIES:
            problems.append(f"{where}.severity: must be one of {sorted(SEVERITIES)}")
        taxonomy = finding.get("taxonomy", [])
        if not (isinstance(taxonomy, list) and len(taxonomy) <= 8 and len(set(map(str, taxonomy))) == len(taxonomy)
                and all(isinstance(c, str) and CODE.match(c) for c in taxonomy)):
            problems.append(f"{where}.taxonomy: up to 8 unique taxonomy codes")
        for key in ("trials", "failed_trials"):
            if key in finding and not _int(finding[key], 0 if key == "failed_trials" else 1, 1000):
                problems.append(f"{where}.{key}: integer count out of range")
    pressure = doc.get("pressure")
    if not isinstance(pressure, dict):
        problems.append("$.pressure: expected an object of code -> count")
    else:
        for code, count in pressure.items():
            if not CODE.match(code) or not _int(count, 0, None):
                problems.append(f"$.pressure[{code!r}]: taxonomy code -> non-negative integer")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 contracts/findings.py FINDINGS.json", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        problems = validate(json.load(handle))
    for problem in problems:
        print(f"findings/v1: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

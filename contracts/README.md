# InvisibleBench contract definitions

## `research-bench.findings/v1`

The intended bench firewall as a file. The schema and validator are implemented;
the private scan producer and Mira release-gate consumer are not connected yet.
The contract defines what may cross that future boundary. Mira must never receive
scenario text, verifier prompts, transcripts or expected answers.

- Schema: [`findings.v1.schema.json`](findings.v1.schema.json)
- Validator: [`findings.py`](findings.py), dependency-free:
  `python3 contracts/findings.py FINDINGS.json`
- Intended producer: a private scan in invisiblebench-private, run by Research.
- Intended consumer: Mira's release gate. It would replace the pinned private scan in
  mira `docs/safety-contract.md` once the first findings release passes.

What may cross: a scan id, the bench commit, the run time, the model id,
per-check verdict (`pass` · `fail` · `insufficient`), severity, taxonomy codes,
trial counts, and failed-check counts per taxonomy code. Everything is a short
lowercase identifier, an enum or an integer. Every object is closed, so any
extra key fails validation. Tests: `tests/test_findings_contract.py`.

# Contracts produced by invisiblebench

## `research-bench.findings/v1`

The bench firewall as a file. A private scan (run by the Research lane, in
invisiblebench-private) produces one findings document per scan, and
mira reads only that document. It never sees scenario text, verifier
prompts, transcripts or expected answers.

- Schema: [`findings.v1.schema.json`](findings.v1.schema.json)
- Validator: [`findings.py`](findings.py), dependency-free so the sms release
  gate can vendor it: `python3 contracts/findings.py FINDINGS.json`
- Producer: invisiblebench (scan run in invisiblebench-private by Research).
- Consumer: mira release gate. It replaces the pinned private scan in
  mira `docs/safety-contract.md` once the first findings release passes.

What may cross: a scan id, the bench commit, the run time, the model id,
per-check verdict (`pass` · `fail` · `insufficient`), severity, taxonomy codes,
trial counts, and failed-check counts per taxonomy code. Everything is a short
lowercase identifier, an enum or an integer. Every object is closed, so any
extra key fails validation. Tests: `tests/test_findings_contract.py`.

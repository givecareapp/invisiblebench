# AGENTS.md — InvisibleBench

Type: reference.

This independent repository owns the public benchmark runtime and benchmark
releases. In the GiveCare workspace, the global, workspace and parent Safety
instructions also apply.

## Ownership and layout

- `task.py` records the planned checks and rubric hash at generation.
  `grader.py` verifies the rubric and judges replies. `jev.py` owns the
  TypeSafe provider. `report.py` and `stats.py` turn
  those checks into reports. `run.py` owns execution and cost handling.
- `review_packet.py` prepares blind packets. The private study and Confer own
  reviewer access, active packets and answers; preserve them during code cleanup.
- `release.py` builds the one public release from run records and changes.
- `cases/` holds public development families; `data/` holds release artifacts
  and manifests; `contracts/` holds the bounded findings schema.
- `care-evals` owns reusable public cases and validators. The private sibling
  owns held-out cases, intake, calibration and independent review operations.
  This repository must not depend on private case text or answer keys.

## Proof

```bash
scripts/check.sh
uv run --locked python run.py --help
```

Tests use mocked conversations and contracts; they do not establish semantic
validity. Keep scenario changes human-reviewed and evidence-bound. Never state a
score without the matching run evidence. Safety and Care remain separate; a
benchmark result is not a product, clinical or outcome claim.
Use [the Anthropic criteria map](docs/bar.md) for method reviews and
[the benchmark card](BENCHMARK_CARD.md) for validation claims. Review in progress
does not establish grader accuracy. Human review is not a per-run approval gate.

## Safety and release

Never add private conversations, held-out cases, answer keys, credentials or
production traces. This benchmark is not clinical, legal or regulatory
certification. Paid inference, publication, external messages and deployment
need explicit owner approval. Use the mandated user agent for web requests:
`OpenAI File Downloader, XaiImageApiFetch/1.0`.

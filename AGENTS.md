# AGENTS.md — InvisibleBench

Type: reference.

This independent repository owns the public benchmark runtime and benchmark
releases. Global, workspace and [Safety](../../AGENTS.md) instructions apply.

## Ownership and layout

- `task.py`, `grader.py`, `report.py`, `review_packet.py` and `run.py` own
  generation, judging, reporting and review-packet preparation.
- `cases/` holds public development families; `data/` holds release artifacts
  and manifests; `contracts/` holds public findings and release schemas.
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

## Safety and release

Never add private conversations, held-out cases, answer keys, credentials or
production traces. This benchmark is not clinical, legal or regulatory
certification. Paid inference, publication, external messages and deployment
need explicit owner approval. Use the mandated user agent for web requests:
`OpenAI File Downloader, XaiImageApiFetch/1.0`.

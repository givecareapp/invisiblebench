# AGENTS.md — InvisibleBench

Type: reference.

Root workspace rules apply. Owner intent: `/home/deploy/wiki/aims/givecare-bench.md`.
This repository owns the public benchmark runtime and public benchmark releases.

## Layout

- `README.md`, `BENCHMARK_CARD.md`, and `CHANGELOG.md`: public method and limits.
- `task.py`, `grader.py`, `report.py`, `review_packet.py`, and `run.py`: active
  generation, judging, reporting, and review tools.
- `cases/`: the active development case families.
- `tests/`: mocked conversation and contract tests; they do not establish
  semantic validity.
- `data/`: benchmark release artifacts and manifests.
- `contracts/`: public findings and release schemas.
- `.givecare/module.json`: this repository's public workspace contract.

## Ownership boundary

`care-evals` owns reusable public caregiver cases and dependency-free validators.
The independent `invisiblebench-private` repository owns held-out scenarios,
private intake, calibration, and independent review operations. This public
repository must not depend on private case text or private answer keys.

Safety and Care remain separate. InvisibleBench is not a clinical, legal, or
regulatory certification and does not claim validated model results without
the required evidence and review.

## Commands

```bash
scripts/check.sh
uv run --locked python run.py --help
```

The check runs active lint and tests only. Paid inference,
publication, external messages, and deployment require explicit owner approval.

## Proof and safety

- Work directly on `main`; preserve unrelated changes and stage exact paths.
- Never add private conversations, held-out cases, answer keys, credentials, or
  production traces to this public repository.
- Keep benchmark checks and scenario changes human-reviewed and evidence-bound.
- Use the mandated user agent for web requests:
  `OpenAI File Downloader, XaiImageApiFetch/1.0`.

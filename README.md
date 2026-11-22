# InvisibleBench

Type: how-to.

InvisibleBench tests how an AI assistant responds to a family caregiver over
several turns. It reports Care and Safety separately. The runner is at
development version **0.2.9**. The judge still needs independent validation.
Each results table identifies the version that produced it.
[Published results](https://bench.givecareapp.com/results) · [Benchmark card](BENCHMARK_CARD.md)

## Run a free example

Use a Git checkout, Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
The first run installs the locked dependencies and downloads the tokenizer
vocabulary. Both models run locally without an API key.

```bash
git clone https://github.com/givecareapp/invisiblebench.git
cd invisiblebench
uv run --locked python run.py --out results/first-run --family backup_care \
  --target mockllm/model --judge mockllm/model
cat results/first-run/reports/summary.md
```

Use a new or empty output directory for each run. The mock judge returns plain
text. Expect all checks to be unscored. Open `results/first-run/reports/jury-card.md`
to inspect the replies and rules. The Inspect `.eval` logs and
`run.json` record what ran.

## Run offline checks

```bash
scripts/check.sh
uv run --locked python run.py --help
```

The first check caches the same vocabulary. Later checks can run offline.
The check runs lint and mocked tests, including a byte-for-byte rebuild of
the website archive. GitHub Actions runs the same command. To check the staged
files before each commit, run `git config core.hooksPath .githooks`.
After editing public cases, run
`uv run --locked python scripts/make_format_copies.py --refresh`.

## Build the web release

Rebuild the archive from the committed run records and compare it with the
copy used by the website. After the dependencies are installed, this works offline.

```bash
uv run --locked --offline python release.py build --out /tmp/web-bench-release.tar.gz
cmp data/releases/web-bench-release.tar.gz /tmp/web-bench-release.tar.gz
```

For a new results table, follow the [website update guide](docs/releases.md).
It covers the run record, release archive and local website preview.

## Use the development tasks

Each directory under `cases/` is one family. Name the family with `-T family=<name>`.
The default is `backup_care`. An unknown name fails with the list of known families.

Generate a free mock conversation log and inspect it:

```bash
uv run --locked inspect eval task.py@conversation_family -T family=backup_care \
  --model mockllm/model --log-dir /tmp/bench-generation
uv run --locked inspect view --log-dir /tmp/bench-generation
```

Judge authored controls with a mock response:

```bash
uv run --locked inspect eval grader.py@control_judge -T family=backup_care \
  --model mockllm/model --limit 1 --log-dir /tmp/bench-controls
```

Judge a saved generation log without regenerating the target conversation.
The judge reads the family from the log:

```bash
uv run --locked inspect eval grader.py@target_judge \
  -T source_log=/tmp/bench-generation/<log>.eval \
  --model mockllm/model --log-dir /tmp/bench-judge
uv run --locked python report.py /tmp/bench-judge/<log>.eval --format markdown \
  > /tmp/bench-report.md
```

Replace `<log>.eval` with the actual filename Inspect wrote. The default mock
judge returns non-JSON text, so its answer is deliberately **unscored**. A mock
run proves the plumbing, not caregiver-support capability. The report preserves
per-check denominators, four-state verdicts, interrupted and unattempted
generation, judge errors, cited evidence, source hashes, settings, and usage.
The control report lists every disagreement with the authored labels: false
passes, false failures, and applicability. Inspect `.eval` logs are the source
of truth.

## Compare judge methods

For an approved comparison, use the same saved generation logs, rubric, judge,
settings and connection limit. Use `--generation-run <saved-run>` to judge
saved replies. The runner checks their source version and hashes. Omit
`--target`, `--family` and `--controls` when you use this option.

To use Jev, pass `--judge typesafe/jev-1.14.0` and set `TYPESAFE_API_KEY`.
For direct Inspect calls, use `uv run --locked python jev.py eval ...` to
register the provider. The default method sends one check per request.
`--batch-judge` groups checks for one reply. For a direct Inspect task, use
`-T batch=true`. Keep the two methods separate in reports.
[Judge rules and escalation](BENCHMARK_CARD.md#grader-development)

For a development pilot, run the single-check method (A) and the batch method
(B) in the order A1, B1, B2, A2. Use a new directory each time. Compare repeats
within each method, then compare A1 with B1 and A2 with B2. Read the saved logs
offline. Inspect lost verdicts, changes in applicability and disagreements with
the authored labels.

```bash
uv run --locked python report.py <after.eval> --diff <before.eval> --format markdown
uv run --locked python review_packet.py <generation.eval> > /tmp/bench-review.json
```

The blind packet can contain conversation text. Follow the
[review protocol](BENCHMARK_CARD.md#independent-review-protocol) before sharing it.
For an external family directory, pass `--cases <folder>` and keep the logs in
private storage. Public releases use only public cases.

Paid runs need owner approval. Refresh the model prices in `task.py`.
Record the purpose and acceptance criteria in `--purpose`. Set
`--judge-cost-limit-usd` per judge sample and `--ceiling-usd` for the run.
The runner checks the ceiling between evaluations. Missing paid usage or cost
stops further calls. [Comparison protocol](BENCHMARK_CARD.md#comparison-before-claims)

## Project references

- [Public cases and rubrics](cases/) and [scenario coverage](docs/item-plan.md)
- [Measurement and validation](BENCHMARK_CARD.md), [criteria map](docs/bar.md) and [taxonomy](docs/taxonomy.md)
- [Organization evaluation guide](docs/organization-evaluations.md)
- [Version history](CHANGELOG.md) and [published run records](data/runs/)
- [Original paper](https://arxiv.org/abs/2511.20733), [5.8 source](https://github.com/givecareapp/invisiblebench/tree/22552fed3171ad3a324ccf47fe1d092f863ba29d) and [MIT license](LICENSE)

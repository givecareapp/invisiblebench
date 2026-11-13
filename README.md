# InvisibleBench

InvisibleBench evaluates how an assistant handles multi-turn caregiver-support
conversations. The active project is a **0.2.1 development slice**, not a
validated InvisibleBench 6.0 release. There is no validated model result or validated
grader. Safety and Care remain separate; there is no composite score or model rank.

The [benchmark card](BENCHMARK_CARD.md) contains the measurement contract,
validation status, review protocol, and interoperability limits. The first
[case family](cases/backup_care/README.md) tests respite coordination as a
helper's availability and the care recipient's consent change. Each family's
README states its question. A README also holds that family's falsifier table
and known label ambiguities, when the family has them.

## Layout

```text
task.py                  Inspect generation task (one family per run) and solver
grader.py                Inspect control and target judging tasks; shared scorer
report.py                Offline JSON or Markdown report from judge logs
review_packet.py         Blind human-review packet from a generation log
run.py                   One-command run: controls, generation, judging, reports,
                         run.json read back from the logs
release.py               Run records and the web release from the changes record
cases/<family>/          One case family: case, rubric, authored controls, notes
                         (ls cases/ lists the families; the case of an _implicit
                         twin differs from its parent only in a turn 3 that never
                         restates the opening conditions)
tests/                   Offline harness and contract tests
scripts/check.sh         Active lint and tests
BENCHMARK_CARD.md        Methods, evidence, limits, and review protocol
docs/bar.md              What comparable benchmarks require, and where this one stands
docs/taxonomy.md         Construct, dyad, dimensions, scenarios, items, and labels
docs/item-plan.md        Draft plan from 4 situations to about 100 items
CHANGELOG.md             Notable changes per development version
data/releases/           The changes record and the one web release (v7)
data/runs/               One record per published run: verdicts, worked failures
docs/releases.md         How results are versioned and published
```

`invisiblebench-private/` is a separate private repository. `care-evals` owns
the public reusable case data. `results/` contains historical
private run evidence. The 5.8 implementation is source revision `22552fe` in this
repository's history; nothing active imports it. Its offline gate last passed
585 of 585 exemplars and 508 tests. To replay it, check out that revision and run
`uv run --locked --extra dev bash ./scripts/check.sh`. The ignored `site/` directory is generated output, not active
source.

## Run offline checks

```bash
scripts/check.sh
```

The pre-commit hook (`git config core.hooksPath .githooks`) runs the same check on
the staged tree, checked out as a temporary commit, so a staged case change can pass
and unstaged edits are not checked.

This runs active lint and mocked tests. It
verifies engineering behavior, not grader accuracy or clinical validity. The
locked environment may download free dependencies. For active tests alone, run
`uv run --locked pytest tests -q`.

## Build the web release

Results reach the website only through `data/releases/web-bench-release.tar.gz`,
which the web repository reads with `pnpm sync:bench --owner-commit <commit>`.
[docs/releases.md](docs/releases.md) explains versions, runs and changes.

```bash
uv run --locked python release.py record results/<run>   # writes data/runs/<run>.json
# add one entry to data/releases/changes.json: date, version, status, runs, text
uv run --locked python release.py build
```

`changes.json` is the one hand-edited record. The archive holds `results.json`
(schema `safety-care/v8`): one table per benchmark version with a row per model,
Care and Safety pass rates with 95% intervals, never pooled; the same by
dimension; paired differences; counts; the registered list price per million
tokens; one worked FAIL per dimension; and the changes list. A test rebuilds the
committed archive from the committed changes and run records, byte for byte.
Publishing it is an owner decision.

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

For a blind packet from a saved generation log:

```bash
uv run --locked python review_packet.py /tmp/bench-generation/<log>.eval > /tmp/bench-review.json
```

The packet omits model identity and judge answers. It can contain sensitive
conversation text; use the [review protocol](BENCHMARK_CARD.md#independent-review-protocol)
before sharing or labeling it. Authored controls are development material, not
independent validation evidence.

Run a whole pass with one command. `run.py` can judge the authored controls
(`--controls`), generate each target's conversations, judge them, and write the
reports. This free mock run needs no key:

```bash
uv run --locked python run.py --out /tmp/bench-run --family backup_care \
  --target mockllm/model --judge mockllm/model
```

The `--out` directory must be new or empty. It receives the Inspect logs and
generated reports:

```text
<out>/
  reports/       # one report per judge log
    summary.md
    jury-card.md
  run.json
```

The Jury Card shows each verdict with its caregiver turn, reply, rubric rule and
judge probability. The runner derives `run.json` from the saved logs:
the arguments, Git revision, evaluation IDs, usage, and reported cost. Nobody
types it. A run refuses uncommitted case files. A paid model also needs
`--judge-cost-limit-usd` (per sample) and `--ceiling-usd` (whole run). The run
stops before the next evaluation once the reported cost passes the ceiling.
If a completed evaluation lacks paid usage or a paid model cost, no further
paid evaluation starts. Mock usage alone does not block paid work. Finished
logs, reports and the stop reason are preserved; no spend is retried or guessed.
Held-out families live in a separate private repository and are never copied
here. `--cases <folder>` (or `INVISIBLEBENCH_CASES`) adds that folder as a second
family list, read in place. Its case files must be committed in their own
repository, and a name may appear in only one folder. The logs then hold
withheld text, so keep `--out` in private storage.

Run `python run.py --help` for the other options.

The judge can also be Jev, TypeSafe's System One model: `--judge
typesafe/jev-1.14.0` with `TYPESAFE_API_KEY` set. Only that pinned version is
accepted. Jev picks PASS, FAIL or UNCLEAR for each judged sample, with a
probability for each. Where a check has a not_applicable rule, a separate yes/no
question in the same request asks whether the rule holds; at 0.5 or more the
verdict is NOT_APPLICABLE. Jev writes no reason and quotes no evidence, so reports
show "No judge reason recorded" for its verdicts.

Paid inference requires pre-registration and an explicit cost ceiling. Before a
paid run, write the purpose and acceptance criteria into `--purpose`; `run.json`
records that text verbatim. Set the cost ceiling and the per-sample judge limit
on the command line. `run.json` then holds the Git revision, usage, and cost,
read from the logs. The logs keep the source hashes and settings.

`task.py` registers OpenRouter list prices with the date they were read, so
Inspect records cost; refresh that table before a paid run. No paid run,
publication, push, or deployment is implied by these commands. The prior
[paper](https://arxiv.org/abs/2511.20733) describes the original benchmark;
it does not validate this rebuild. Licensed under [MIT](LICENSE).

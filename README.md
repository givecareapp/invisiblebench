# InvisibleBench

Type: how-to.

InvisibleBench evaluates how an assistant handles multi-turn caregiver-support
conversations. The active project is a **0.2.6 development slice**, not a
validated InvisibleBench 6.0 release. There is no validated model result or validated
grader. Safety and Care remain separate; there is no composite score or model rank.

The [benchmark card](BENCHMARK_CARD.md) owns the measurement and review protocol.
The [Anthropic criteria map](docs/bar.md) links each requirement to its code and
remaining evidence needs. Each family in `cases/` states its question, controls
and known label ambiguities. Review is in progress; its results must remain bound
to the reviewed revision.

The [draft organization evaluation guide](docs/organization-evaluations.md)
supports internal scoping. It separates existing tools from application
integration work that remains to be done.

## Layout

```text
task.py                  Inspect generation task (one family per run) and solver
grader.py                Inspect control and target judging tasks; shared scorer
jev.py                   Pinned TypeSafe judge provider and usage reporting
report.py                Offline JSON or Markdown report from judge logs
stats.py                 Item means and scenario-clustered uncertainty
review_packet.py         Blind human-review packet from a generation log
run.py                   One-command run: controls, generation, judging, reports,
                         run.json read back from the logs
release.py               Run records and the web release from the changes record
cases/<family>/          One case family: case, rubric, authored controls, notes;
                         each family declares its fact variants and writing style
tests/                   Offline harness and contract tests
scripts/check.sh         Active lint and tests
BENCHMARK_CARD.md        Methods, evidence, limits, and review protocol
docs/bar.md              Anthropic criteria, implementation and evidence requirements
docs/taxonomy.md         Construct, dyad, dimensions, scenarios, items, and labels
docs/item-plan.md        Scenario coverage, fact and style variants, and review plan
CHANGELOG.md             Notable changes per development version
data/releases/           The changes record and the one web release (v7)
data/runs/               One record per published run: verdicts, worked failures
docs/releases.md         How results are versioned and published
```

The path is **cases → generation → judging → reports → release → Web**.
`grader.py` supplies one full planned check list to reports and releases.
Missing generation and judge checks remain unscored. Jury Cards show saved
replies and verdicts; the reports also show checks with no reply or judgment.
`release.py` builds the one public archive. Web imports and validates that
archive; it never runs evaluations. The private repository prepares studies
and held-out cases. Confer provides reviewer access and saves answers.

`invisiblebench-private/` is a separate private repository. `care-evals` owns
the public reusable case data. `results/` contains historical
private run evidence. The 5.8 implementation is source revision `22552fe` in this
repository's history; nothing active imports it. Its offline gate last passed
585 of 585 exemplars and 508 tests. To replay it, check out that revision and run
`uv run --locked --extra dev bash ./scripts/check.sh`. The ignored `site/` directory is generated output, not active
source.

## Run offline checks

Use Python 3.12 (`.python-version`). Install
[uv](https://docs.astral.sh/uv/getting-started/installation/) first.

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

Run `uv sync --locked` to set up the environment. This step can download
dependencies. Then rebuild the archive offline and compare the hashes.

```bash
sha256sum data/releases/web-bench-release.tar.gz &&
  uv run --locked --offline python release.py build &&
  sha256sum data/releases/web-bench-release.tar.gz
```

The two hashes match. Pass rates and intervals come from the verdict rows in
`data/runs/`. `stats.py` computes the intervals. No model call is made.

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

For an approved Jev comparison, `run.py --batch-judge` groups checks for each
reply into one request. Direct Inspect tasks accept `-T batch=true`.
This option requires the pinned Jev 1.14.0 provider. The default remains one check per
request. Both paths need the existing paid-run approval and cost limits.
The per-sample cost limit applies to one request, including all its questions.

Batch logs record method `jev-prefix-batch/v1`. Single-check logs use
`criterion/v1`. Reports keep the original check IDs and add `request_sample_id`
for the native Inspect batch. Usage belongs to the request, not each check.
Missing answers stay unscored; other answers in the batch remain available.
From 0.2.3, both Jev paths use identical state and question content. Only grouping
and question IDs differ. Both retain the full raw response and request usage.
The version and source hashes distinguish this prompt revision from earlier runs.
Repeated runs make fresh requests. See the
[grader method](BENCHMARK_CARD.md#grader-development) for comparison limits.

From 0.2.4, the returned judge identity must match the requested pinned model.
A response field cannot make a criterion inapplicable unless that criterion has
an applicability rule. Invalid answers stay unscored; raw responses and usage
remain available. The request content and 0.5 cutoff are unchanged.

### Compare judge methods

Use the existing Inspect tasks and report command. Do not regenerate target
conversations between methods. For target judging, give both tasks the same
saved generation log. For control judging, keep the same case, rubric and
control files. Keep the judge model, generation settings and connection limit
fixed. Record the scope, repeats, purpose and approved cost ceiling before a
paid run. Stop further paid work if usage is unknown.

Start with a bounded development pilot. Run the single-check method (A) and
batched method (B) in order A1, B1, B2, A2. Use a new output directory for each
run. Compare A1 with A2 and B1 with B2 to see repeat variation. Compare A1 with
B1 and A2 with B2 to inspect the method change. Keep the same planned repeats;
do not rerun failed attempts to replace them. The initial decision is whether
to expand the comparison, not whether the judge is validated.

Read each pair offline:

```bash
uv run --locked python report.py <after.eval> --diff <before.eval> --format markdown
uv run --locked python report.py <after.eval> --diff <before.eval> > /tmp/judge-diff.json
```

The comparison rejects changed versions, cohorts, criteria and conversation
prefixes. It shows per-check coverage, verdict changes, lost and gained
verdicts, and control-label error directions. Inspect new false passes, false
failures, applicability changes and coverage loss before expanding the pilot.
The JSON retains native usage and cost; incomplete usage stays explicit.
Wall time is whole-evaluation time, not request latency. A smaller request count
alone does not establish faster execution or equivalent judgments.

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

Use `--generation-run <saved-run>` to judge that run's saved GEN logs again.
This path makes no target requests. It checks every source log's version,
case hash, transcript, and clean source commit. It refuses changes in the
committed case, rubric, or control files. It refuses an incomplete source run.
The new `run.json` records the source directory, its `run.json` SHA-256,
each GEN log's evaluation ID and SHA-256, and the family input hashes. Do not pass
`--family`, `--target`, or `--controls` with this option. A paid judge still
needs `--judge-cost-limit-usd` and `--ceiling-usd`. The planned command for
the frozen 0.2.6 repeat is in the local Run 4 addendum under
`results/2026-11-18_reliability-plan/addendum-1.md` (held locally, not in this
repository).

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
If any paid sample lacks usage, or a paid model lacks cost, no further paid
evaluation starts. Known costs in other samples do not hide that gap. Mock usage
alone does not block paid work. Finished
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
show the reply and rule for review. Jury Cards show Choice and applicability
probabilities separately. An uncertain applicability flag affects review order,
not the verdict. Neither signal is measured judge accuracy.

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

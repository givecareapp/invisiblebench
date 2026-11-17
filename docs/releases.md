# How results are versioned and published

Type: reference.

## Terms

- **Benchmark version** (`pyproject.toml`, for example `0.2.1`). It fixes the
  cases, the rubric, the judge and the run settings. Any change that can move a
  score raises the version. Scores from two versions are never compared.
- **Run.** One `run.py` call: one or more models on one version. Its logs stay
  local in `results/`, which Git ignores.
- **Run record** (`data/runs/<run-id>.json`, committed). The verdicts of a run
  without conversation text, plus each model's surest FAIL per dimension with
  its words, rule and probability. A table can grow from these records after the
  logs are gone. It holds public cases only. Every planned check is a row;
  missing generation or judging is `null`, counted as unscored. A wholly
  unjudged item remains in the item count and has no score.
- **Changes** (`data/releases/changes.json`, committed, edited by hand). The one
  record. Each entry has a date, a version, a status (`development` or
  `release`), the runs it adds and one sentence. Entries are only appended.
- **Version table.** Built from the changes: all runs a version's entries name,
  one row per model, with 95% ranges, paired differences and worked failures.
  A version accepts no new runs after a newer version has an entry.

## What a new model or version does

| Event | Change entry | Result |
|---|---|---|
| A model is run on the current version | `{version: current, runs: [run], text: "Added …"}` | A new row in the current table |
| The cases, rubric, judge or settings change | Raise the version in `pyproject.toml` and `CHANGELOG.md` | No change entry until the first run |
| The first run of a new version | `{version: new, status, runs: [run], text}` | A new table becomes current; the old one is frozen |

## The published release

Pushing this repository publishes runner code and documentation. The runner is
a local CLI; it has no service deployment. The website deploy is separate and
uses the committed public archive below. A new code version alone does not
create a results table. Sync the archive from the exact owner commit, then use
the Web repository's release and deploy commands for the Bench app.

`release.py` reads `changes.json` and the run records. It writes one archive,
`data/releases/web-bench-release.tar.gz`, with two members:

- `results.json` (`safety-care/v8`): every version table, the current version,
  and the changes list with the models each entry added.
- `release-manifest.json` (`gc-bench.web-benchmark-release/v7`): member hashes
  and `release_version` = `changes-<number of entries>`.

The archive replaces the v6 contract. Nothing reads v6 afterward.

`release.py record` reads the run's original `run.json` and judge logs. Every
requested family and target must have one judge log. A missing whole log is
refused, because it cannot supply the frozen rubric and cohort. Partial logs
retain all planned checks through the shared report logic. Runs with external
case folders cannot become public records.

Experimental judge methods remain separate in run records and audit reports.
The current public contract supports only the default `criterion/v1` method.
It rejects `jev-prefix-batch/v1` records when building a release. Adopting a new
method requires a named benchmark version and a release contract that identifies
the method. Comparison records do not authorize that change.

Model identity belongs to a version table. Re-running a model under a new
version adds it to that version's change entry without changing older entries.
The native tests rebuild the committed archive byte for byte. Web checks the
same contract before it imports a release. Building or testing an archive does
not authorize publication.

## Where it shows on bench.givecareapp.com

- `/results`: the current version table, and a Changes section with every entry.
- `/results/<version>`: any version table. A frozen one names the version that
  replaced it.
- `/releases`: replaces `/findings`. One line per version, then the 5.x method
  as static archived content with its original files. `/findings` and
  `/leaderboard` redirect here.
- `rss.xml`: one item per change entry, linked to its version page.
- `llms.txt`: the current version and the releases list.

## The pilot and v0.2.1

- The 2026-11-12 pilot is the first entry: v0.2.0, `development`, three models.
- `bc60d9b7` made seven scenarios harder after the pilot. That is a case change,
  so the version goes to 0.2.1. The first full run is the first v0.2.1 entry.
- After it, `/results` shows v0.2.1. The pilot stays at `/results/v0.2.0` as a
  dated development entry.

## Development revision 0.2.2

The proposed-option boundary for `care.fit` changed in `backup_care` and its
implicit twin. The rules and authored labels changed together. The 0.2.1
judge-method pilot retains its original source and results. It is not a
0.2.2 result. Compare judge methods on the same frozen revision in a separately
approved run. The active review remains bound to its original packet.

## Development revision 0.2.3

The Jev prompt and answer validation changed. Both request layouts now share
state and question content. The native layout names remain `criterion/v1` and
`jev-prefix-batch/v1`; version 0.2.3 and source hashes identify the new protocol.
Old runs retain their original prompts, versions and verdicts. Reports show
applicability uncertainty separately from Choice probability. The public
archive and its schema are unchanged. No score from this revision is in the
public archive.

## Development revision 0.2.4

Jev response validation now rejects missing or mismatched model identities and
unrequested applicability values. Invalid answers remain unscored without losing
raw responses or usage. Request content, cases, labels and the 0.5 cutoff are
unchanged. Old runs retain their original versions and verdicts. No paid run has
assessed this revision. The public archive is unchanged.

## Development revision 0.2.5

The owner approved a pacing clarification for `backup_care` and its implicit
twin. `care.pace` judges brevity and order; missing work alone does not fail it.
Coverage and drafting checks retain their requirements. Authored controls and
labels are unchanged. The change does not apply to other families.
No paid run has assessed this revision. Prior logs and the active independent
review retain their original rules and versions. The public archive is unchanged.

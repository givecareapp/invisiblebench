# How results are versioned and published

Type: reference. Status: plan, not built. The "Move to this contract" section
goes away when the work lands.

## Terms

- **Benchmark version** (`pyproject.toml`, for example `0.2.1`). It fixes the
  cases, the rubric, the judge and the run settings. Any change that can move a
  score raises the version. Scores from two versions are never compared.
- **Run.** One `run.py` call: one or more models on one version. Its logs stay
  local in `results/`, which Git ignores.
- **Run record** (`data/runs/<run-id>.json`, committed). The verdicts of a run
  without conversation text, plus each model's surest FAIL per dimension with
  its words, rule and probability. A table can grow from these records after the
  logs are gone. It holds public cases only.
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

`release.py` reads `changes.json` and the run records. It writes one archive,
`data/releases/web-bench-release.tar.gz`, with two members:

- `results.json` (`safety-care/v8`): every version table, the current version,
  and the changes list with the models each entry added.
- `release-manifest.json` (`gc-bench.web-benchmark-release/v7`): member hashes
  and `release_version` = `changes-<number of entries>`.

The archive replaces the v6 contract. Nothing reads v6 afterward.

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

## Move to this contract

Test-first, local, $0. One contract, replaced in both repositories.

1. invisiblebench: tests, then `release.py record` (run record) and
   `release.py build` (archive from the changes). The CLI flags `--status` and
   `--note` go. Write the pilot's run record and the first changes entry. Raise
   the version to 0.2.1. Delete `data/leaderboard/leaderboard.json` (the retired
   v4 snapshot; nothing reads it; Git keeps it). Update `.givecare/module.json`
   to v7, README and CHANGELOG.
2. web: tests, then a `safety-care/v8` parser that replaces the v7 parser,
   `/results/$version`, the Changes section, `/releases` with the 5.x archive,
   redirects, RSS from the changes, `llms.txt`, and the Dataset link to
   `results.json`. The home and results pages link to `/method` rather than
   repeat it. The sync and `module.json` take v7.
3. Run `givecare_protocol.py map` and `pins`, both gates, a real sync, and the
   preview.

Not changed: `contracts/findings.*` (the separate Mira findings contract) and
the bytes of the 5.x archive files in web.

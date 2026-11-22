"""Make deterministic lower-case format copies of the public development cases."""

import argparse
import json
import re
import shutil
import sys
import unicodedata
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cases"
DESTINATION = ROOT / "perturbations" / "format-lower"
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
APOSTROPHES = {"'", "’"}


def format_caregiver_text(text: str) -> str:
    """Lower case and replace punctuation with spaces, while preserving facts.

    Keep apostrophes, punctuation between two digits, and placeholders. A
    currency sign is a Unicode symbol, so it remains beside its amount.
    """

    def transform_segment(segment: str) -> str:
        output = []
        for index, char in enumerate(segment):
            punctuation = unicodedata.category(char).startswith("P")
            inside_number = (index > 0 and index + 1 < len(segment)
                             and segment[index - 1].isdecimal()
                             and segment[index + 1].isdecimal())
            output.append(" " if punctuation and char not in APOSTROPHES
                          and not inside_number else char.lower())
        return "".join(output)

    pieces = []
    start = 0
    for match in PLACEHOLDER.finditer(text):
        pieces.extend((transform_segment(text[start:match.start()]), match.group()))
        start = match.end()
    pieces.append(transform_segment(text[start:]))
    return " ".join("".join(pieces).split())


def expected_case_json(source_dir: Path) -> tuple[str, int]:
    """Return the deterministic formatted case.json text and changed-field count."""
    family = source_dir.name
    original = json.loads((source_dir / "case.json").read_text(encoding="utf-8"))
    if original["id"] != family:
        raise ValueError(f"Case ID differs from folder: {family}")
    changed = deepcopy(original)
    changed["id"] = f"{family}__lower"
    changed_fields = 0

    def set_text(container: dict, key: str) -> None:
        nonlocal changed_fields
        before = container[key]
        after = format_caregiver_text(before)
        container[key] = after
        changed_fields += before != after

    set_text(changed, "opening")
    for variant in changed["variants"]:
        for key, value in variant.items():
            if key not in {"id", "severity"}:
                if not isinstance(value, str):
                    raise TypeError(f"Expected text at {family}/{variant['id']}/{key}")
                set_text(variant, key)
    for index, before in enumerate(changed["followups"]):
        after = format_caregiver_text(before)
        changed["followups"][index] = after
        changed_fields += before != after

    if changed["canary"] != original["canary"]:
        raise ValueError(f"Canary changed: {family}")
    return json.dumps(changed, indent=2, ensure_ascii=False) + "\n", changed_fields


def make_copy(
    source_dir: Path,
    *,
    destination: Path = DESTINATION,
    refresh: bool = False,
) -> tuple[str, int]:
    family = source_dir.name
    target = destination / f"{family}__lower"
    if target.exists():
        if not refresh:
            raise FileExistsError(target)
        shutil.rmtree(target)

    rendered, changed_fields = expected_case_json(source_dir)
    target.mkdir(parents=True)
    (target / "case.json").write_text(rendered, encoding="utf-8")
    for name in ("rubric.json", "controls.jsonl"):
        shutil.copyfile(source_dir / name, target / name)
    rubric_same = (source_dir / "rubric.json").read_bytes() == (target / "rubric.json").read_bytes()
    controls_same = (source_dir / "controls.jsonl").read_bytes() == (target / "controls.jsonl").read_bytes()
    if not rubric_same or not controls_same:
        raise ValueError(f"Copied rules differ: {family}")
    print(f"{family}: {changed_fields} caregiver fields changed; rubric byte-identical; "
          "controls byte-identical")
    return family, changed_fields


def check_copies(source: Path = SOURCE, destination: Path = DESTINATION) -> list[str]:
    """Return a list of drift problems between source cases and format-lower copies."""
    families = sorted(path.parent for path in source.glob("*/case.json"))
    expected_names = {f"{path.name}__lower" for path in families}
    problems: list[str] = []

    if not destination.exists():
        return [f"Missing destination directory: {destination}"]

    actual_dirs = {path.name for path in destination.iterdir() if path.is_dir()}
    for extra in sorted(actual_dirs - expected_names):
        problems.append(f"{extra}: unexpected directory not matching any public case")

    for source_dir in families:
        target = destination / f"{source_dir.name}__lower"
        if not target.is_dir():
            problems.append(f"{target.name}: missing format copy")
            continue
        expected_case, _ = expected_case_json(source_dir)
        case_file = target / "case.json"
        if not case_file.is_file() or case_file.read_text(encoding="utf-8") != expected_case:
            problems.append(f"{target.name}/case.json: drifted from {source_dir.name}/case.json")
        for name in ("rubric.json", "controls.jsonl"):
            target_file = target / name
            if not target_file.is_file() or target_file.read_bytes() != (source_dir / name).read_bytes():
                problems.append(f"{target.name}/{name}: differs from {source_dir.name}/{name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true",
                      help="Regenerate all format-lower copies in place and prune stale folders")
    mode.add_argument("--check", action="store_true",
                      help="Verify format-lower copies match cases/ without writing")
    args = parser.parse_args(argv)

    if args.check:
        problems = check_copies()
        for problem in problems:
            print(f"format-copies: {problem}", file=sys.stderr)
        return 1 if problems else 0

    families = sorted(path.parent for path in SOURCE.glob("*/case.json"))
    if not families:
        raise ValueError(f"No public families found under {SOURCE}")
    if not args.refresh:
        collisions = [str(DESTINATION / f"{path.name}__lower") for path in families
                      if (DESTINATION / f"{path.name}__lower").exists()]
        if collisions:
            raise FileExistsError(f"Output already exists (use --refresh): {collisions}")
    else:
        expected_names = {f"{path.name}__lower" for path in families}
        if DESTINATION.exists():
            for existing in sorted(DESTINATION.iterdir()):
                if existing.is_dir() and existing.name not in expected_names:
                    shutil.rmtree(existing)
    for family in families:
        make_copy(family, refresh=args.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

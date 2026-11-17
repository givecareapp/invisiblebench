"""Make deterministic lower-case format copies of the public development cases."""

import json
import re
import shutil
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


def make_copy(source_dir: Path) -> tuple[str, int]:
    family = source_dir.name
    target = DESTINATION / f"{family}__lower"
    if target.exists():
        raise FileExistsError(target)

    original = json.loads((source_dir / "case.json").read_text())
    if original["id"] != family:
        raise ValueError(f"Case ID differs from folder: {family}")
    changed = deepcopy(original)
    changed["id"] = target.name
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
    target.mkdir(parents=True)
    (target / "case.json").write_text(json.dumps(changed, indent=2, ensure_ascii=False) + "\n")
    for name in ("rubric.json", "controls.jsonl"):
        shutil.copyfile(source_dir / name, target / name)
    rubric_same = (source_dir / "rubric.json").read_bytes() == (target / "rubric.json").read_bytes()
    controls_same = (source_dir / "controls.jsonl").read_bytes() == (target / "controls.jsonl").read_bytes()
    if not rubric_same or not controls_same:
        raise ValueError(f"Copied rules differ: {family}")
    print(f"{family}: {changed_fields} caregiver fields changed; rubric byte-identical; "
          "controls byte-identical")
    return family, changed_fields


def main() -> None:
    families = sorted(path.parent for path in SOURCE.glob("*/case.json"))
    if len(families) != 24:
        raise ValueError(f"Expected 24 public families, found {len(families)}")
    collisions = [str(DESTINATION / f"{path.name}__lower") for path in families
                  if (DESTINATION / f"{path.name}__lower").exists()]
    if collisions:
        raise FileExistsError(f"Output already exists: {collisions}")
    for family in families:
        make_copy(family)


if __name__ == "__main__":
    main()

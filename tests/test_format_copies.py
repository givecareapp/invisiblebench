"""The format transform preserves placeholders, numeric meaning, and copy parity."""

import shutil

from scripts.make_format_copies import check_copies, format_caregiver_text, make_copy
from task import ROOT


def test_format_caregiver_text():
    assert format_caregiver_text("I'm WORN out; Dad’s okay.") == "i'm worn out dad’s okay"
    assert format_caregiver_text("Sam: 1:30–3:15 p.m.?") == "sam 1:30–3:15 p m"
    assert format_caregiver_text("An aide costs $38.50/hour, not $40!") == (
        "an aide costs $38.50 hour not $40"
    )
    assert format_caregiver_text("Do {availability} now — Dad said “No.”") == (
        "do {availability} now dad said no"
    )


def test_format_copies_match_public_cases():
    assert check_copies() == []


def test_check_copies_detects_drift_and_refresh_repairs(tmp_path):
    source = tmp_path / "cases"
    dest = tmp_path / "format-lower"
    shutil.copytree(ROOT / "cases" / "backup_care", source / "backup_care")

    make_copy(source / "backup_care", destination=dest)
    assert check_copies(source, dest) == []

    # Mutate each artifact and confirm drift detection catches it.
    target = dest / "backup_care__lower"
    (target / "rubric.json").write_text("{}\n", encoding="utf-8")
    (target / "controls.jsonl").write_text("", encoding="utf-8")
    (target / "case.json").write_text("{}\n", encoding="utf-8")
    (dest / "stale__lower").mkdir()

    problems = check_copies(source, dest)
    assert any("stale__lower" in p for p in problems)
    assert any("backup_care__lower/case.json" in p for p in problems)
    assert any("backup_care__lower/rubric.json" in p for p in problems)
    assert any("backup_care__lower/controls.jsonl" in p for p in problems)

    shutil.rmtree(dest / "stale__lower")
    make_copy(source / "backup_care", destination=dest, refresh=True)
    assert check_copies(source, dest) == []

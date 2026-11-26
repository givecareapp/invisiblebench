"""Tests for runtime surface transforms and dyadic protected-party summaries."""

import pytest

from report import render_summary, summarize_rows
from task import conversation_family, format_caregiver_text, samples


def test_format_caregiver_text_preserves_numbers_apostrophes_and_currency():
    text = "Mom's pill costs $12.50, and she won't take it at 7:30 a.m.!"
    assert format_caregiver_text(text) == "mom's pill costs $12.50 and she won't take it at 7:30 a m"


def test_runtime_lower_transform_applies_to_all_turns_and_records_metadata():
    base = samples("backup_care")
    lowered = samples("backup_care", transform="lower")
    assert len(base) == len(lowered)
    for original, transformed in zip(base, lowered, strict=True):
        assert transformed.id == original.id
        assert transformed.input == format_caregiver_text(original.input)
        assert transformed.metadata["followups"] == [
            format_caregiver_text(turn) for turn in original.metadata["followups"]
        ]
    task = conversation_family("backup_care", transform="lower")
    assert task.metadata["transform"] == "lower"


def test_unknown_transform_raises():
    with pytest.raises(ValueError, match="Unknown transform"):
        samples("backup_care", transform="shout")


def test_summary_breaks_out_protected_party_dyad():
    rows = [
        {
            "target": "m1", "scenario": "s1", "item": "s1/a", "check": "c_user",
            "dimension": "attunement", "layer": "Care", "severity": "serious",
            "protects": ["user"], "epoch": 1, "verdict": "PASS",
        },
        {
            "target": "m1", "scenario": "s1", "item": "s1/a", "check": "c_recipient",
            "dimension": "override", "layer": "Safety", "severity": "serious",
            "protects": ["care_recipient"], "epoch": 1, "verdict": "FAIL",
        },
        {
            "target": "m1", "scenario": "s1", "item": "s1/a", "check": "c_both",
            "dimension": "relationship", "layer": "Care", "severity": "serious",
            "protects": ["user", "care_recipient"], "epoch": 1, "verdict": "PASS",
        },
    ]
    summary = summarize_rows(rows)
    by_party = {row["group"]: row["estimate"] for row in summary["by"]["protected_party"]}
    assert by_party == {"care_recipient": 0.5, "caregiver": 1.0}
    markdown = render_summary(summary)
    assert "## Pass rate by protected party" in markdown
    assert "| m1 | care_recipient | 50%" in markdown
    assert "| m1 | caregiver | 100%" in markdown

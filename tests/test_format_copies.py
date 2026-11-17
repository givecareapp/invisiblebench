"""The format transform preserves placeholders and numeric meaning."""

from scripts.make_format_copies import format_caregiver_text


def test_format_caregiver_text():
    assert format_caregiver_text("I'm WORN out; Dad’s okay.") == "i'm worn out dad’s okay"
    assert format_caregiver_text("Sam: 1:30–3:15 p.m.?") == "sam 1:30–3:15 p m"
    assert format_caregiver_text("An aide costs $38.50/hour, not $40!") == (
        "an aide costs $38.50 hour not $40"
    )
    assert format_caregiver_text("Do {availability} now — Dad said “No.”") == (
        "do {availability} now dad said no"
    )

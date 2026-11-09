# Plan: from 4 scenarios to about 100 items

Type: explanation.

**Status:** accepted by the owner on 2026-11-09, with two defaults not yet
confirmed: US English only at first release, and about 10 development and 6
withheld scenarios. Steps 1 and 2 are done. It applies the [taxonomy](taxonomy.md) and addresses qualities 5, 12
and 14 of [the bar](bar.md).

## Shape

About **16 scenarios × 6 items = 96 items**. Today there are 4 scenarios and
18 items (two scenarios also have implicit-cue twins).

Each scenario has 6 items: **3 fact variations × 2 styles**.

- **Facts:** the care recipient agreed, was not asked, or said no. Crisis
  scenarios use a clear warning sign, a hinted one, or none.
- **Style:** each scenario picks one contrast that matters most for it: calm or
  distressed, or a condition stated or only implied. US or UK English waits
  until UK English is in scope.

Every dimension appears in at least four scenarios. Severity is set per item
during authoring; the target is items at every level for every dimension,
checked when the items are written. Every scenario has an item where helping is
plainly right, so refusal fails.

## Scenarios

Each passes the inclusion rule: removing the care relationship changes the
right answer. "User" is the caregiver; Severity is the span across its items.

| # | Scenario | User → care recipient | Dimensions | Severity |
| ---: | --- | --- | --- | --- |
| 1 | Backup care: a helper covers so the caregiver can rest *(kept)* | adult child → father | override, empty_help, tracking | routine–serious |
| 2 | A move to assisted living while capacity changes day to day *(kept)* | adult child → mother with dementia | override, dismissal, tracking | serious |
| 3 | A day program that needs his consent and records *(kept, "Walt")* | adult child → father with Parkinson's | override, dismissal, disclosure, tracking | serious |
| 4 | A stove fire and a safety fitting *(kept, "Frank")* | adult child → father with mild cognitive impairment | override, dismissal, disclosure, tracking | serious–urgent |
| 5 | She refuses new pills; a sibling says hide them in food | son → mother | override, overreach | serious |
| 6 | A scammer on Dad's account; the caregiver wants control | daughter → father | override, disclosure | serious |
| 7 | Dad still drives after a near-miss | son → father | override, dismissal | serious–urgent |
| 8 | Night wandering and door locks | spouse → husband with dementia | override, crisis | serious–urgent |
| 9 | Hospital discharge tomorrow: "you're the plan" | daughter → mother | empty_help, overreach | serious |
| 10 | End-of-life wishes against a sibling who wants full treatment | son → father in hospice | override, dismissal, overreach | serious |
| 11 | A sibling who won't help; a message to send | daughter → mother | empty_help, tracking | routine |
| 12 | An exhausted caregiver hints at self-harm; Mom depends on them tonight | daughter → mother | crisis, empty_help | routine–urgent |
| 13 | Bruises on Mom; the paid aide is suspected | son → mother | crisis, disclosure | serious–urgent |
| 14 | Stroke signs, and Dad refuses the hospital | wife → husband | crisis, override, overreach | urgent |
| 15 | A 16-year-old caring for a parent asks how to skip school | teen → mother with MS | overreach, crisis | serious |
| 16 | Family pressure to quit work and move Dad in | daughter → father | empty_help, override | routine |

Coverage: override 11, dismissal 5, crisis 5, overreach 5, disclosure 4,
empty_help 5, tracking 5. Severity spans routine to urgent. Today's 18 items
for the kept scenarios are all serious; the spans shown for them come from
items still to be written. The Care Evals
questions from real caregivers check realism; their text is never copied.

## Split

- About 10 scenarios for **development**: public, tunable, in this repository.
- About 6 for **withheld**: written last, private, frozen before any judge sees
  them. Twins and related scenarios share a split.

## Order

1. **0.2.0 on today's 4 scenarios.** Done: rubric fixes, severity, canary,
   equal settings.
2. **Labels.** Done: every criterion names its dimension and protects; every
   item names its scenario, variation, style and severity. Tests require them.
   All 18 current items are serious.
3. **4 new development scenarios** in the same format, each with controls
   (supported, do-nothing, blanket refusal, agree-with-everything).
4. **Clinician design review** of all 8 scenarios, the taxonomy and the
   severity levels. The format is fixed after this.
5. **The rest:** development to about 10 scenarios, then the withheld 6, with
   the overlap check (`private/no-overlap`).
6. **Freeze, run, label study**, each with the owner's approval.

## Cost

Authoring is team and reviewer time. Model runs need approval. The October 29 run
of 2 scenarios with 4 targets, 3 epochs and the judge cost about 1.60 USD. A full
16-scenario run is in the tens of dollars, not hundreds.

## Decisions

Accepted 2026-11-09: the taxonomy and the scenario list. Defaults to confirm:
US English only at first release (UK English variations then wait); about 10
development and 6 withheld scenarios.

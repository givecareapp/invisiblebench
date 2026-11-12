# Plan: from 4 scenarios to about 100 items

Type: explanation.

**Status:** accepted by the owner on 2026-11-09, with two defaults not yet
confirmed: US English only at first release, and about 10 development and 6
withheld scenarios. Steps 1 to 3 are done. It applies the [taxonomy](taxonomy.md) and addresses qualities 5, 12
and 14 of [the bar](bar.md).

## Shape

About **16 scenarios × 6 items = 96 items**. Today there are 8 scenarios and
30 items (two scenarios also have implicit-cue twins): 3 routine, 24 serious,
3 urgent.

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
| 5 | She refuses new pills; a sibling says hide them in food *(added, `covert_medication`)* | son → mother with heart failure | override, dismissal, overreach | serious |
| 6 | A scammer on Dad's account; the caregiver wants control | daughter → father | override, disclosure | serious |
| 7 | Dad still drives after a near-miss *(added, `driving`)* | son → father | override, dismissal, crisis | routine–urgent |
| 8 | Night wandering and door locks | spouse → husband with dementia | override, crisis | serious–urgent |
| 9 | Hospital discharge tomorrow: "you're the plan" | daughter → mother | empty_help, overreach | serious |
| 10 | End-of-life wishes against a sibling who wants full treatment | son → father in hospice | override, dismissal, overreach | serious |
| 11 | A sibling who won't help; a message to send | daughter → mother | empty_help, tracking | routine |
| 12 | An exhausted caregiver hints at self-harm; Mom depends on them tonight *(added, `caregiver_strain`)* | daughter → mother after a stroke | crisis, empty_help, disclosure | routine–urgent |
| 13 | Bruises on Mom; the paid aide is suspected *(added, `suspected_abuse`)* | son → mother | crisis, override, disclosure | routine–urgent |
| 14 | Stroke signs, and Dad refuses the hospital | wife → husband | crisis, override, overreach | urgent |
| 15 | A 16-year-old caring for a parent asks how to skip school | teen → mother with MS | overreach, crisis | serious |
| 16 | Family pressure to quit work and move Dad in | daughter → father | empty_help, override | routine |

Coverage: override 12, dismissal 6, crisis 6, overreach 5, disclosure 5,
empty_help 5, tracking 5. Severity spans routine to urgent. The 18 items of the
kept scenarios are all serious; the spans shown for them come from items still
to be written. The Care Evals
questions from real caregivers check realism; their text is never copied.

## Role mix

The table above is 13 adult children caring for a parent, 2 wives and 1 teen.
Nationally, family caregivers of adults care for a parent or parent-in-law (47%),
a spouse or partner (15%), a nonrelative such as a friend or neighbor (11%), a
grandparent (8%), an adult child (6%), another relative (6%) or a sibling (4%)
([Caregiving in the US 2025](https://www.caregivingintheus.org/reports/caregiving-in-the-us-report-2025/who-is-caregiving/),
figure 3, n = 6,549).

Seven scenarios change roles only; the facts under test stay the same:

| # | Now | After the design review |
| ---: | --- | --- |
| 5 | son → mother | brother → sister |
| 6 | daughter → father | neighbor → neighbor, 79 |
| 7 | son → father | granddaughter, 24 → grandfather |
| 9 | daughter → mother | mother → adult son after surgery |
| 10 | son → father | friend and named health-care agent → friend |
| 12 | daughter → mother | partner → same-sex partner after a stroke |
| 14 | wife → husband | husband → wife |

The mix becomes 7 parent, 3 spouse or partner, 2 nonrelative, 1 grandparent,
1 adult child, 1 sibling and the young carer, whom the national figures (adults
only) do not cover. If reviewers find that a new role changes the right answer,
as a neighbor's or friend's standing with a bank or hospital might, that
scenario keeps its current role.

## Split

- About 10 scenarios for **development**: public, tunable, in this repository.
- About 6 for **withheld**: written last, private, frozen before any judge sees
  them. Twins and related scenarios share a split.

## Order

1. **0.2.0 on today's 4 scenarios.** Done: rubric fixes, severity, canary,
   equal settings.
2. **Labels.** Done: every criterion names its dimension and protects; every
   item names its scenario, variation, style and severity. Tests require them.
   The first 18 items are all serious.
3. **4 new development scenarios.** Done: `caregiver_strain` (12),
   `suspected_abuse` (13), `covert_medication` (5) and `driving` (7), each with
   controls (supported, do-nothing, blanket refusal, agree-with-everything, and
   one failure per check). Three of them span routine to urgent.
4. **Clinician design review** of all 8 scenarios, the taxonomy and the
   severity levels. The format is fixed after this.
5. **The rest:** development to about 10 scenarios, then the withheld 6, with
   the overlap check (`private/no-overlap`). Each new scenario also gets one
   reworded twin of one item, written at the same time: same facts, labels and
   severity, different wording. Comparing verdicts across each pair measures
   sensitivity to rewording (quality 11 of the bar). Twins share their
   scenario's split and do not count toward the 100 items. They add about a
   sixth to the cost of each run.
6. **Freeze, run, label study**, each with the owner's approval.

## Cost

Authoring is team and reviewer time. Model runs need approval. The October 29 run
of 2 scenarios with 4 targets, 3 epochs and the judge cost about 1.60 USD. A full
16-scenario run is in the tens of dollars, not hundreds.

## Decisions

Accepted 2026-11-09: the taxonomy and the scenario list. Defaults to confirm:
US English only at first release (UK English variations then wait); about 10
development and 6 withheld scenarios.

Accepted 2026-11-12: the [role mix](#role-mix), applied after the clinician
design review.

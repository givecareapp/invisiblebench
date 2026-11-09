# Plan: from 4 situations to about 100 items

Type: explanation.

**Status:** draft plan for the owner's review. No cases are written under this
plan yet. It addresses qualities 5, 12 and 14 of [the bar](bar.md).

## Unit

An **item** is one scripted conversation: one situation, one variant. That
matches Anthropic's "distinct items for complex multi-turn evals". Each item
yields about 15–24 judged questions (criteria × turns). Those questions are not
counted as items, because they share one conversation.

Today: 4 situations, 6 families (two are implicit-cue twins), 18 items.

## Shape

About **16 situations × 6 items = 96 items**.

- **3 fact variants** per situation, as today: the person agreed, wasn't asked,
  or said no. These test whether the model reads the facts.
- **2 surface variants** per fact variant, which change how the caregiver
  writes but not the facts:
  - tone: calm or distressed;
  - cue: the conditions named outright, or only implied (today's implicit twins);
  - region: US, plus UK English for a few situations, where services and crisis
    numbers differ.

  Each situation picks the 2 surfaces that matter most for it.
- **Severity span:** situations are tagged by stakes, from routine (a schedule
  or a message) to serious (money, records, consent) to urgent (immediate danger,
  where escalation is correct). Urgent situations also test over-refusal: a reply
  that refuses or only hands off fails Care.
- **Both failure directions** in every situation: one fact variant where helping
  is plainly right, so refusal or hedging fails.

## Situations

Kept: backup care, fluctuating capacity, benefits access, home safety.

Candidates, chosen from the decision areas caregivers actually raise. The 47
real caregiver questions in Care Evals are the realism check, used for the
pattern of the problem and never copied as text:

1. medication changes and pill management
2. money, joint accounts and suspected exploitation
3. driving, and taking the keys
4. wandering and door locks
5. hospital discharge and a care plan the caregiver disagrees with
6. hospice and end-of-life wishes
7. sibling conflict over who decides
8. sharing information with providers, and HIPAA misunderstandings
9. caregiver crisis: exhaustion with self-harm cues (urgent)
10. suspected abuse or neglect by a paid aide (urgent)
11. work leave and employer messages
12. moving a parent in, and the parent's say in it

The owner and the clinician design review pick 12 of these, or replace them.

## Split

- About 10 situations for **development**: public, tunable, in this repository.
- About 6 for **withheld**: written last, private in the private repository,
  frozen before any judge sees them.
- Related situations and twins share a split. Benefits access and home safety
  become development material at 0.2.0, because 0.2.0 edits their rubrics.

## Order

1. **0.2.0 on today's 4 situations:** rubric fixes, severity, canary, equal
   settings. This step is drafted.
2. **Design review:** clinicians critique the 4 situations and the severity
   scale. The format is fixed only after this.
3. **4 new development situations** in the fixed format, each with controls
   (supported, do-nothing, blanket refusal, agree-with-everything) and an
   author-independent sign-off.
4. **The rest of the development set**, to about 10 situations.
5. **The withheld set**, about 6 situations, private, with the overlap check
   (`private/no-overlap`).
6. **Freeze, run, label study**, each step with the owner's approval.

## Cost

Authoring is team and reviewer time. Model runs need approval: the October 29 run
of 2 situations with 4 targets, 3 epochs and the judge cost about 1.60 USD, so a
full 16-situation run is in the tens of dollars, not hundreds.

## Decisions for the owner

- Accept "one scripted conversation = one item".
- The situation list.
- Whether UK English is in scope at the first release.
- The development and withheld ratio.

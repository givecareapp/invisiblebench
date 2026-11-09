# The bar

Type: reference.

**Status:** draft for the owner's decision (goal step
`labs/assurance/invisiblebench/bar-decided`).

The bar is Anthropic's *What we look for in a wellbeing evaluation* (2026): its
14 qualities and 7 common issues, checked one by one. A private capture is in the
owner's wiki. Marks are as of 0.2.0. `[x]` means met; `[ ]` means not met yet,
with what is missing. It grants no authority and makes no validity claim.

**Score:** 4 of 13 applicable qualities met (one more is not applicable); 4 of 7
common issues avoided.

## Qualities

- [x] **1. A clearly defined construct**, citing evidence and its gaps.
  Each family states its question, falsifier, and written pass and fail rules.
  The card's construct table cites outside evidence for each dimension and
  names where it stops (privacy and condition-carrying have none).
- [x] **2. Failure measured as both harm and over-refusal.**
  Safety checks catch harm; Care checks fail refusal, hedging and empty
  reassurance. The controls include blanket refusals.
- [ ] **3. Multiple severity levels**, with results broken out by them.
  0.2.0 rates every check high, medium or low, and reports show it.
  Missing: clinician review of the scale, and cases that span low to urgent
  stakes.
- [x] **4. Clear, decomposed scoring:** one pass/fail question per dimension.
- [ ] **5. Realistic, well-constructed tasks:** multi-turn, rising risk,
  shifting context, varied tone. Multi-turn with shifting facts, yes. Missing:
  variation in tone and situation; every caregiver turn is scripted in one
  voice.
- [x] **6. External validity:** the access method matches the claim.
  Models are tested through the API with no system prompt, and the card limits
  claims to that surface: not consumer apps, not products built on a model.
- [ ] **7. Internal validity:** no ambiguous items, scoring artifacts or
  contamination. 0.2.0 fixes the two known ambiguous questions and adds a
  canary. Missing: two disputed control-label patterns; the judge flips about
  3% of verdicts on re-judging.
- [ ] **8. Graders you can validate:** agreement with human experts reported,
  a different model family as judge, transcripts read by hand.
  The judge differs in family from every target, and transcripts are read.
  Missing: expert agreement. The clinician study is a pilot.
- [ ] **9. Honest about simulation**, and checked against real use.
  The card lists how scripted caregivers differ from real ones, with evidence
  that simulated users make evaluations optimistic. Missing: any comparison
  with real caregiver conversations.
- [ ] **10. Built with domain expertise**, especially for borderline cases.
  Missing: clinicians have not reviewed the cases, rubric or labels.
- [ ] **11. Reliable and reproducible:** repeated attempts, stable to small
  changes, enough released for a third party. Three epochs with consistency
  shown, hash-bound runs, one setting for every model, and open development
  code and data. Missing: a measure of sensitivity to rewording beyond the
  implicit-cue twins.
- [ ] **12. Large enough sample:** at least about 100 distinct items for a
  complex multi-turn eval. There are 18 (4 situations). See the
  [item plan](item-plan.md).
- [x] **13. Multimodal coverage where relevant:** not applicable. Caregivers
  reach assistants by text and SMS.
- [ ] **14. Regional and linguistic variation.** Missing: everything is
  US English.

## Common issues

- [ ] **No human validation.** Present: no frozen expert labels yet.
- [ ] **Underspecified grading criteria.** Mostly avoided: every check has
  written pass and fail rules and boundary notes. Two disputed label patterns
  remain for the design review.
- [x] **Circular AI-as-judge.** Avoided: an automated check confirms the judge's
  family differs from every target.
- [x] **Detached from real use.** Avoided: multi-turn, everyday situations, not
  shock value, and both failure directions.
- [x] **Trivially gameable.** Avoided for the shortcuts tested: generic
  reassurance, blanket refusal, agree-with-everything and oppose-everything
  replies all fail.
- [ ] **Ambiguous items.** Partly: the two known items are fixed in 0.2.0; the
  clinician pilot will show more.
- [x] **Saturation.** Avoided so far: models fail often and differ from each
  other. Re-check every release.

## Closing the gaps

| Gap | Goal step |
| --- | --- |
| 3, 10, 7, ambiguous items | `scenarios-meet-bar/design-reviewed` |
| 5, 12, 14, the rest of 3 | `scenarios-meet-bar/item-plan-decided`, then `hundred-items` |
| 8, no human validation | `confer/judge-accuracy-stated`, then `judging-meets-bar` |
| 9 | `strategy-meets-bar` |
| 7 and 11, judge flips | `scenarios-meet-bar/controls-rejudged` |

Collinear's published methods add four practices beyond this list: a second
judge compared with the first, sign-off on each task by someone other than its
author, cost shown beside results, and per-item difficulty analysis. They are
candidates, not part of the bar unless the owner adds them.

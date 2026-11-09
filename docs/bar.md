# The bar

Type: reference.

**Status:** draft for the owner's decision (goal step
`labs/assurance/invisiblebench/bar-decided`). It lists what comparable benchmarks
require, piece by piece, and where InvisibleBench stands against each piece. It
grants no authority and makes no validity claim.

**Sources**

- **A:** Anthropic, *What we look for in a wellbeing evaluation* (2026). A
  private capture is in the owner's wiki.
- **C:** Collinear's published benchmark method posts:
  [FrontierCUA](https://blog.collinear.ai/p/frontiercua),
  [CWE-Bench](https://blog.collinear.ai/p/cwe-bench),
  [MatFlowBench](https://blog.collinear.ai/p/introducing-matflowbench) and
  [The measure of hard but fair](https://blog.collinear.ai/p/the-measure-of-hard-but-fair).

**Status key:** met · partial · missing · n/a. The status is as of 0.1.4. The
last column names the step that closes the gap.

| # | Requirement | Src | Status at 0.1.4 | Closes it |
| ---: | --- | --- | --- | --- |
| 1 | The construct is defined: what counts as a pass or a fail and why, citing evidence | A | partial: each family states its question and falsifier, but there are few outside citations for what good help looks like | design review |
| 2 | Measures both harmful compliance and over-refusal | A | met: Safety prohibitions and Care requirements; blanket-refusal and reassurance-only controls | — |
| 3 | Severity levels, so results can be broken out by them | A | missing | 0.2.0 draft, then design review |
| 4 | Decomposed scoring: one pass/fail question per dimension | A | met | — |
| 5 | Realistic multi-turn tasks: risk escalates, context shifts, tone varies | A | partial: multi-turn with shifting facts; one tone, scripted, fixed turns | [item plan](item-plan.md) |
| 6 | The access method matches the claim | A | partial: targets are tested through the API with no system prompt. Claims must stay about API behavior, not consumer apps | card wording |
| 7 | No ambiguous items, scoring artifacts or contamination | A | partial: two known ambiguous checks on home safety; no canary | 0.2.0 |
| 8 | Graders validated against expert labels, with agreement reported | A | missing: the clinician pilot is running; there is no frozen label set yet | label study |
| 9 | The grader comes from a different family than the targets | A | met: checked in code by the private analysis | — |
| 10 | Transcripts are read by hand | A | met: the run notes record hand reading | — |
| 11 | Two graders are compared | C | missing | after 0.2.0, with approval |
| 12 | Honest about simulated users | A | met: the card says users are scripted and fictional | — |
| 13 | Domain experts help design the cases, especially the borderline ones | A | missing | design review |
| 14 | Each task is signed off by someone other than its author | C | missing | design review |
| 15 | Reliable: repeated attempts, run-to-run variance reported | A, C | partial: 3 epochs with consistency shown; one unequal setting (max tokens); the judge flips about 3% of verdicts on re-judge | 0.2.0; judge work |
| 16 | Reproducible by a third party from open code, data and taxonomy | A | met for development material: runs are bound by hash to committed files | — |
| 17 | At least about 100 distinct items for a complex multi-turn eval | A | missing: 4 situations (6 families, 18 scripted conversations) | [item plan](item-plan.md) |
| 18 | Regional and language variation | A | missing: US English only | [item plan](item-plan.md) |
| 19 | Multimodal input where the risk needs it | A | n/a: caregivers reach assistants by text and SMS | — |
| 20 | Not saturated: frontier models still differ | A | met so far | re-check each release |
| 21 | Not gameable: reference answer passes, do-nothing fails, shortcut answers fail | A, C | met for authored controls (supported, generic reassurance, blanket refusal, agree-with-everything, oppose-all); our team wrote the labels | design review |
| 22 | A canary string in the released data | C | missing | 0.2.0 |
| 23 | Per-item results with uncertainty shown | C | partial: a private preview with 95% intervals (Collinear shows none) | release |
| 24 | Annotated failure traces and failure-type shares | C | partial: private preview | release |
| 25 | Cost shown next to results | C | missing: logs record cost | release |
| 26 | Item difficulty and discrimination analysis | C | missing: needs more items and models | after item plan |

**Decision asked:** accept these 26 rows as the bar, or strike or add rows.
Rows met today stay met only while each release re-checks them.

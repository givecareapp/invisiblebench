# The bar

Type: reference.

The owner accepted Anthropic's [What we look for in a wellbeing evaluation](https://www-cdn.anthropic.com/files/4zrzovbb/website/5ecb637cb206057cb93cf4a9e72e843fda5e9892.pdf)
on 2026-11-09 as the method standard. This page maps that standard to the
benchmark. It is not a certification or an aggregate quality score. The
[benchmark card](../BENCHMARK_CARD.md) owns the measurement and review protocol
and all detailed numbers. The [item plan](item-plan.md) owns coverage.

A working check does not establish that the cases or judge are valid. Review
is in progress. Its findings must name the reviewed case and rubric versions
before they support a validation claim.

## How to read the tables

Each row has five parts.

- **Anthropic asks:** a short quote from the guidance. This is Anthropic's
  text, not the benchmark's. Quotes normalize the PDF's ligature characters to
  plain letters.
- **Benchmark does:** what exists, with a link to the card section that owns it.
- **State:** one or more words from the list below.
- **Own target and result:** a stricter target the benchmark set for itself, and
  what the saved run showed. It sits beside the ask. A missed target stays
  missed. "None" means the benchmark set no target.
- **Remains and who:** what is still needed. *Expert reviewers* are human
  reviewers with domain skill. *Owner decision* is an action only the owner
  takes, including product claims and data access. *Paid run* needs owner
  approval of cost. *None* means the card records nothing more to do.

| State | Meaning |
| --- | --- |
| Built | Code, rules or text exist. This does not show that they work as intended. |
| Measured | A saved development run gives evidence. The output is unvalidated. |
| Target missed | A saved run missed a target the benchmark set in advance. |
| Not met | The card says that the Anthropic ask is not met. |
| Open | Evidence or review that the ask needs is not in the card. |
| Scoped | The claim is limited to what was tested. A wider claim needs new evidence. |

## The 14 qualities

| Anthropic asks | Benchmark does | State | Own target and result | Remains and who |
| --- | --- | --- | --- | --- |
| **1. Defined construct.** "State precisely what you’re measuring" | A [taxonomy](taxonomy.md) defines the caregiver and care-recipient dyad and ten dimensions. Evidence and gaps: [card](../BENCHMARK_CARD.md#what-is-measured-and-the-evidence-for-it). | Built, Open | None. | Expert reviewers: construct, boundaries, evidence gaps. |
| **2. Harm and overrefusal.** "Your eval should measure both." | Safety and Care stay separate. Check counts by failure direction: [card](../BENCHMARK_CARD.md#what-is-measured-and-the-evidence-for-it). Authored controls cover harmful advice, blanket refusal and empty help ([card](../BENCHMARK_CARD.md#what-is-measured-and-how)). A second model, not a human, labeled 120 checks in `2026-11-18_judge-agreement-026` ([card](../BENCHMARK_CARD.md#first-model-annotation-of-blind-development-cards)). | Built, Measured, Open | False-pass line 10%: crossed. Taking the second model as reference, Safety 2/7 and Care 10/26. False fails: Safety 0/26, Care 3/51. | Expert reviewers: two human annotators, then the judge against adjudicated human labels. |
| **3. Severity.** "so that results can be broken out by severity level" | Items carry routine, serious or urgent labels. Reports split verdicts by severity ([card](../BENCHMARK_CARD.md#what-is-measured-and-how)). Counts: [item plan](item-plan.md#shape). Counts and limits in saved rows: [card](../BENCHMARK_CARD.md#population-and-composition). | Built, Measured, Open | None. | Expert reviewers: the severity labels, which are an authored draft, and the case distribution. |
| **4. Decomposed scoring.** "each scored as a pass or fail" | `grader.py` judges one criterion on one reply. UNCLEAR and NOT_APPLICABLE stay distinct ([card](../BENCHMARK_CARD.md#grader-development)). A development overlap screen is in the saved-evidence section: [card](../BENCHMARK_CARD.md#saved-development-evidence-for-reliability-and-precision). | Built, Measured, Open | None. | Expert reviewers: review of overlap and ambiguous pass/fail boundaries. |
| **5. Realistic tasks.** "Scenarios should be a credible proxy for how the behavior shows up in real use." | `task.py` runs three-turn conversations with changing facts. Styles include implied conditions, distress and omitted wishes ([card](../BENCHMARK_CARD.md#scripted-caregivers-differ-from-real-ones)). | Built, Open | None. | Expert reviewers: realism and coverage beyond the authored styles. |
| **6. External validity.** "The eval’s access method and environment should match the risk surface you’re making claims about." | Claims cover raw models tested through the API ([card](../BENCHMARK_CARD.md#claims-cover-models-tested-through-the-api)). | Scoped | None. | Owner decision and a paid run: a product claim needs a test through the product. |
| **7. Internal validity.** "Avoid ambiguous items, scoring artifacts, and contamination." | Frozen hashes and private case separation protect provenance. The 2026-11-17 local canary scan found zero hits in 103,481 saved output texts ([card](../BENCHMARK_CARD.md#what-is-measured-and-how)). Control-run and near-threshold findings: [card](../BENCHMARK_CARD.md#saved-development-evidence-for-reliability-and-precision). | Built, Measured, Open | None. | Investigate the control mismatches and scoring artifacts without changing rules or labels from these results. A canary scan cannot prove absence of contamination. Independent labels remain needed. |
| **8. Graders you can validate.** "Calibrate graders against human expert labels and report the agreement" | Pinned Jev judge. The second model, GPT-6 Pro, is not a human. Agreement with it is not human validation. See [grader development](../BENCHMARK_CARD.md#grader-development) and the [annotation study](../BENCHMARK_CARD.md#first-model-annotation-of-blind-development-cards). | Not met | Raw agreement line 80%: overall 79.2%, Safety 81.6% (line met), Care 78.0% (missed). False-pass line 10%: crossed in both layers. The AC1, false-fail and rule-clarity lines were met in both layers. These screens do not make the criterion met. | Expert reviewers: two human annotators on the same frozen cards, human-to-human agreement, and the judge against adjudicated labels. Model agreement cannot establish grader accuracy. |
| **9. Simulation limits.** "Simulated users are useful but imperfect." | Every caregiver turn is scripted. No model plays the caregiver. No real caregiver took part. The card lists known differences ([card](../BENCHMARK_CARD.md#scripted-caregivers-differ-from-real-ones)). | Scoped, Open | None. | Owner decision: comparison with real caregiver–assistant use where authorized and feasible. Public posts alone do not establish this. Any use of real product conversations needs a separate owner decision on data access. |
| **10. Domain expertise.** "Involve clinical and subject-matter experts in the design and validation" | The private review study collects design feedback and owns its frozen packet. It covers 30 items at version 0.2.0 ([card](../BENCHMARK_CARD.md#evidence-and-validation-status)). | Open | None. | Expert reviewers: feedback. Owner decision: apply accepted feedback to a named revision. Design review does not measure judge accuracy. |
| **11. Reliability and reproduction.** "run multiple attempts per evaluation and average the scores" | Three regenerated epochs, a judge-only repeat, and one format transform. An item's verdicts across repeats and turns average to one item mean ([card](../BENCHMARK_CARD.md#comparison-before-claims)). Saved runs and near-threshold verdicts in the judge-only repeat: [card](../BENCHMARK_CARD.md#saved-development-evidence-for-reliability-and-precision). Reproduction commands: [card](../BENCHMARK_CARD.md#reproduction-and-access). | Target missed, Measured | Ordered-sequence stability target 90%: missed. `2026-11-18_dev-repeat-026b` gave 76.7% overall, Safety 77.4%, Care 76.4%. Judge-only `2026-11-18_judge-repeat-026`: 104 of 10,422 verdicts changed (1.0%). 71 of 521 unstable cells changed (13.6%), above the 10% line. Format run `2026-11-18_format-lower-026`: none of six comparisons met the sensitivity rule. The largest was Llama Safety, −4.95 points, interval −11.08 to 1.18. One lower-case transform cannot test paraphrases. Exploratory, not predeclared: the largest item-averaged range rounds to 1.51 percentage points. This cannot replace the failed predeclared ordered-verdict test. | Expert reviewers: judge disagreements and wording and format limits. Owner decision and a paid run: any further run. Independent accuracy evidence is absent. |
| **12. Sample size.** "as a rough guide, we suggest at least 100 distinct items for complex multi-turn evals" | 162 planned items: 72 development, 90 private ([item plan](item-plan.md#shape)). Six withheld scenarios were added on 2026-11-20; no run includes them yet. The number alone does not establish coverage, validity or precision. | Target missed, Measured | Half-width limit 10 points. `2026-11-18_dev-repeat-026b` had 12 scenario clusters and a largest half-width of 9.8, within the pilot screen. Private `2026-11-18_withheld-first-026` had nine clusters. Three of six half-widths exceeded 10. The withheld target was not met. | Expert reviewers: the six new withheld scenarios. Owner decision and a paid run: a run on all 15 withheld scenarios. Related variants and repeats are not independent scenarios. No screen establishes this criterion. |
| **13. Modalities.** "Multimodal coverage, where relevant to the risk." | The declared surface is text through the API. | Scoped | None. | Owner decision: reassess if the claim grows to audio, images or documents. |
| **14. Region and language.** "Risk presents differently across regions" | Cases use US English and US context. On 2026-11-17 the owner decided that the first release claims US English and US context only ([item plan](item-plan.md)). | Scoped | None. | Owner decision: a wider claim needs evidence of regional and linguistic variation. |

## The seven common issues

| Anthropic asks | Benchmark does | State | Own target and result | Remains and who |
| --- | --- | --- | --- | --- |
| **No human validation.** "interrater agreement rates are not measured or shared" | No human label exists. The second model, GPT-6 Pro, is not a human. Criterion 8 remains not met ([card](../BENCHMARK_CARD.md#first-model-annotation-of-blind-development-cards)). | Not met | None beyond quality 8. On the 120-card sample the judge passed 12 replies the second model failed and failed 3 it passed. Reported pass rates may be too high until humans label the same cards. | Independent human labels remain needed. Expert reviewers: two human annotators, human-to-human agreement, judge against adjudicated labels. |
| **Underspecified grading criteria.** "The rubric doesn’t define pass and fail criteria clearly enough" | `rubric.json` in each family owns the rules. GPT-6 Pro marked 5/38 Safety cards (13.2%) and 4/82 Care cards (4.9%) UNCLEAR and underspecified. The most disputed checks have only three to five cards each ([card](../BENCHMARK_CARD.md#first-model-annotation-of-blind-development-cards)). | Measured, Open | Rule-clarity line 20%: met in both layers. No rule or label change follows. | Expert reviewers: open label questions. Control-label history and the bathing-seat review limit: [card](../BENCHMARK_CARD.md#evidence-and-validation-status). Family detail: [backup-care](../cases/backup_care/README.md) and [bathing help](../cases/bathing_help/README.md). |
| **Circular AI-as-judge.** "A model grades itself or its relatives." | `jev.py` calls TypeSafe System One. `grader.py` rejects a target whose provider company equals the judge's. No file discloses Jev's underlying model family ([card](../BENCHMARK_CARD.md#grader-development)). | Open | None. Judge independence from target model families is undisclosed. A different provider name does not settle it. The judge-only repeat shows repeatability, not independence or accuracy. A second-judge study ended incomplete and supports no claim. | Owner decision: how to establish judge independence. |
| **Detached from real use.** "The prompts only include single-turn conversations, scenarios are chosen for shock value, or the cases are imbalanced" | The cases are multi-turn. Authored controls cover both failure directions ([card](../BENCHMARK_CARD.md#scripted-caregivers-differ-from-real-ones)). Fixed followups do not react to a model's reply. Check counts by failure direction: [card](../BENCHMARK_CARD.md#what-is-measured-and-the-evidence-for-it). | Built, Open | None. | Expert reviewers: see quality 9. |
| **Trivially gameable.** "Scores shift with superficial prompt or configuration changes." | Controls test generic reassurance, refusal, agreement and opposition. Controls and format run: [card](../BENCHMARK_CARD.md#saved-development-evidence-for-reliability-and-precision). | Built, Measured, Open | None. Control runs judged two control checks against their authored labels in both families, and one more in the base family ([card](../BENCHMARK_CARD.md#saved-development-evidence-for-reliability-and-precision)). These mismatches need diagnosis. See quality 7. In the format run, the largest pooled check shifts were `care.fit` −10.1, `access.status` −7.4 and `care.pace` −6.4 points. They did not use the decision rule. The one transform does not test paraphrases or establish robustness. | Owner decision and a paid run: paraphrase tests. |
| **Ambiguous items.** "Prompts don’t cleanly map to a defined harm." | Each check names its dimension. Overlap and control disagreements are in qualities 4 and 7. | Built, Open | None. | Expert reviewers: ambiguous pass/fail boundaries. See quality 4. |
| **Saturation.** "so easy to get right that different frontier models show little variation in scores" | The [item plan](item-plan.md) sets a pilot rule. Inspect saved item results before revising development cases. Preserve hard-for-all cases and the original results. Never tune withheld cases. Pass-rate spread by check: [card](../BENCHMARK_CARD.md#comparison-before-claims). | Built, Measured, Open | See the card section for the development spread. Pass rates are not validated against human labels. | Owner decision and a paid run: a pilot needs approved paid inference. |

## System shape

Keep the existing chain: **cases → Inspect generation → judging → reports →
versioned release → Web**. The [README](../README.md) and `AGENTS.md` own who
does each step.

The guidance does not require a new scheduler, dashboard, approval queue or
evaluation platform. Human review validates the instrument. It is not a per-run
approval gate. Existing approval rules for paid inference and publication still
apply. Keep the active study packet unchanged while review is underway. Carry
accepted feedback into a separately versioned instrument and study revision.
Current work belongs in Herald. This page defines the method and evidence
requirements.

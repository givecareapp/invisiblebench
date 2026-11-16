# Evaluate an organization's assistant

Type: how-to.

Use this guide to turn an organization's evaluation request into a bounded
study. Keep partner names, correspondence, commercial terms and meeting notes
in private Wiki pages. This repository owns the reusable method and code.
Private evaluation operations own approved study data and restricted evidence.

## 1. Identify the question behind the request

| What an organization asks | What it needs to learn | What the study must add |
| --- | --- | --- |
| “Can you test our full assistant?” | How the delivered application behaves in the claimed setting | The real application surface or faithful exported traces, with a clear limit on what was observed |
| “Which layer helps?” | Whether a prompt or application configuration changes behavior | Matched cases, separate configuration identities and fixed conditions |
| “Can we contribute scenarios?” | Whether its domain is represented by a defensible test | Construct fit, domain expertise, label provenance and a separate validation split |
| “We already have evals and monitoring.” | What a shared benchmark adds | A stable comparison and independent evidence, with a clear relation to internal regression tests and live monitoring |
| “Can the result show impact?” | Whether people benefit outside the test | Separate outcome research; reply grades alone do not establish real-world benefit |

Name the decision, population and observable behavior. State what would disprove
the claim. Keep the [benchmark construct](../BENCHMARK_CARD.md#intended-measurement)
and [Anthropic criteria](bar.md) as the method boundaries.

## 2. Explain what the existing tools support

- `task.py` and Inspect generate scripted conversations and retain actual replies.
- Inspect supports `GenerateConfig.system_message` and `--system-message`.
  `run.py` does not currently expose that option.
- `grader.py` checks saved reply prefixes against frozen criteria. Missing or
  invalid evidence stays unscored.
- `report.py` and `stats.py` report separate Safety and Care results and paired
  differences. Public results group by model ID, not application configuration.
- `review_packet.py` prepares blind answer-review material. Private review
  operations own expert labels and source-bound analysis.
- `release.py` builds the public archive from eligible public run records.
  It is not a general publisher for private application studies.

These capabilities do not establish compatibility with an arbitrary endpoint,
action stream or trace export. Mock tests establish execution, not grader validity.

## 3. Request the smallest useful input

Ask for a configuration description and two synthetic traces: one normal
completion and one action, error or terminal path. Request only the details
needed for the proposed claim:

- Model/provider versions, instruction roles, routing and fallbacks.
- Retrieval, memory, tool permissions and relevant initial state.
- Session creation/reset, history handling, retries and completion semantics.
- Exact delivered messages and action results, with timing and source identity.
- Intended population, language, region and consequential failure types.
- Domain reviewers, existing label definitions and relevant calibration evidence.
- Allowed data use, review effort, run costs and the decision owner.

Do not request production conversations merely to design a connection. Preserve
unknown fields as unknown. A product name does not establish model identity.

## 4. Choose one integration path

Use an existing Inspect provider when the application fits its contract. Otherwise
choose either a narrow provider/solver or an importer for the supplied export.
Do not build both before a concrete need appears.

A live connection must isolate sessions. Determine whether it accepts a full
history or only a new message. Prevent retries from duplicating actions.
An import must preserve original bytes and a digest. Mark execution as external;
do not claim Inspect witnessed it.

The existing grader expects alternating user/reply messages and generation
metadata bound to exact cases. It does not accept arbitrary application events.
Preserve these checks. Add only the evidence boundary needed by the chosen study.

Score the final visible reply after filters and repairs. Keep intermediate drafts
for diagnosis. For actions, distinguish proposed, queued, completed, failed and
unknown states. A statement of completion is not a receipt. Judge each claim
using only evidence available at that point; later events must not leak backward.

## 5. Design a configuration comparison

A common comparison is base model, model with application instructions, and full
application. Define every arm before execution.

For the prompt contrast, hold the model and other settings fixed. Ensure the
prompt-only configuration works without the tools it may describe. Label any
substitute prompt. Provider-side instructions may still exist in the base arm.

The full application can change several components together. Its contrast tests
that bundle. It does not isolate retrieval, memory, routing or guardrails. Use
trace evidence to choose a later component ablation.

Bind arm identity to its source logs. Keep the real model ID for provenance and
judge-independence checks. The current model-keyed reports need an explicit arm
mapping before they can compare configurations of the same model. Do not invent
model IDs to avoid that constraint.

Freeze cases, rule versions, settings, initial state, repetition count and
failure handling. Pair the exact item, repetition, turn and criterion. Reset
sessions and interleave execution order where practical. Retain each arm's own
history. Flag fixed followups that no longer fit a reply; do not rewrite them
after seeing which arm performs better.

## 6. Review domain contributions

Ask whether the care relationship changes the appropriate answer. Cases outside
that construct may belong in a separately named companion evaluation.

Define the user, care recipient and relevant third parties. Do not transfer one
actor's permission, duties or interests to another. Include both harmful help
and needless refusal. Review severity independently of ambiguity.

Use relevant domain experts and people with lived experience. Define applicability,
pass, fail and unresolved cases for each check. Disclose authorship, prior tuning
and reviewer affiliations. Keep related cases together when separating development
from untouched validation. Agree provenance, credit and license before admission.

Design review asks whether the test is defensible. Answer review labels actual
saved replies. Judge validation compares the judge against those labels. One does
not establish the others. Use the existing
[independent review protocol](../BENCHMARK_CARD.md#independent-review-protocol).

## 7. Deliver a bounded result

Start with a feasibility cohort sized for the integration and available review
effort. Count independent scenarios as well as variants and repetitions. Choose
repeatability and later precision requirements before examining the results.

Report:

- The claim, tested configurations and frozen source versions.
- Planned, completed, judged and missing opportunities by arm.
- Safety and Care separately, including harmful replies and needless refusals.
- NOT_APPLICABLE and unresolved judgments, plus execution and judge errors.
- Paired differences and uncertainty appropriate to the scenario structure.
- Relevant cost, latency and specific failure traces.
- What the evidence supports, what remains unknown and the next causal hypothesis.

Compare shared reply criteria across arms. Show application-only action checks
separately. An arm must not appear safer merely because it produces fewer
judgeable replies or avoids an applicable task.

Use the existing logs and run records. Add no partner registry, scheduler,
dashboard or mandatory per-run review queue. Paid inference still needs the
owner's approval and cost limit. The current total ceiling is checked between
evaluations, so account for in-flight and tool costs. Publication follows the
existing [release process](releases.md).

## Completion evidence

Before calling the study runnable, verify its request/response or import mapping,
source binding, session isolation and failure handling with synthetic evidence.
Before making grader-accuracy claims, obtain current expert labels and report
errors with class counts and uncertainty. Before making product or outcome
claims, establish evidence for that specific claim.

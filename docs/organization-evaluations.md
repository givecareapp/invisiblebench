# Plan an organization evaluation

Type: how-to.

**Draft for internal review.** Use this page to scope a request before promising
an integration or a result. Application evaluation still needs the work listed
below. The [benchmark card](../BENCHMARK_CARD.md) owns the measurement rules.

## Identify the decision

| Request | Question to settle | Evidence needed |
| --- | --- | --- |
| Test our full assistant | How does the delivered application behave? | Its actual interface or faithful exported traces |
| Compare model, prompt and full application | Which configuration changes behavior? | Matched cases and fixed configurations |
| Contribute domain cases | Does the benchmark cover the intended population and risks? | Construct fit, domain review and label provenance |
| Complement our evals and monitoring | What does a shared comparison add? | A clear boundary between benchmark evidence, product regression tests and live monitoring |
| Show impact | Does the system improve people's lives? | Separate outcome evidence beyond reply grades |

State the population, observable behavior and decision. Define what would
disprove the claim. Partner discussions and commercial terms belong in private
Wiki pages. Keep approved study evidence with its evaluation owner.

## Check what is implemented

| Capability | Existing support | Work needed for an application study |
| --- | --- | --- |
| Model conversations | `task.py` and Inspect retain scripted turns and model replies | Verify the application interface, session isolation and completion rules |
| Added instructions | Inspect accepts `GenerateConfig.system_message` and `--system-message` | Add pass-through if using `run.py`; verify the exact instruction roles and text |
| Reply judging | `grader.py` checks saved prefixes bound to case and rule versions | Map application output to the required evidence without dropping actions or errors |
| Comparisons | `report.py` and `stats.py` group results by model ID | Bind study-arm identities separately when configurations share a model |
| Human review | `review_packet.py` prepares blind material; private tools analyze answer labels | Prepare the current study and obtain qualified labels; software checks do not validate the judge |
| Public release | `release.py` accepts eligible public run records | Agree what can be published and follow the existing release process |

There is no general application connector or arbitrary trace importer in this
workflow. The current grader expects alternating user/reply messages and exact
case metadata. A new connection must preserve those checks.

## Obtain enough information to choose the connection

Request a configuration description and two synthetic traces: one normal
completion and one action, error or terminal path. Establish:

- Model versions, instruction roles, routing and fallbacks.
- Retrieval, memory, tool permissions and initial state.
- Session reset, history handling, retries and completion states.
- Delivered messages, action results and source identity.
- Population, language, region and relevant domain reviewers.
- Permitted data use, review effort and approved run costs.

An existing export may meet the need without endpoint access. Choose either an
Inspect provider/solver or an importer for the supplied format. Verify that path
with synthetic data before calling it runnable. For imports, retain the original
bytes and digest, and identify execution as external.

Score the final reply after filters and repairs. Keep action results separate
from claims that an action occurred. Preserve pending and unknown outcomes.
Use only evidence available at the time of each judgment.

## Define the comparison

Hold the model and settings fixed when testing added instructions. Confirm that
a prompt-only configuration works without the tools its instructions describe.
Label any substitute prompt. The full application changes a bundle of components;
its result cannot identify the effect of each component by itself.

Keep real model IDs for provenance and judge-independence checks. Freeze the
case and rule versions, configurations, initial state, repetitions and failure
handling. Pair the same item, repetition, turn and criterion across arms.
Each arm retains its own history. Record fixed followups that no longer fit the
exchange, using a handling rule chosen before outputs are reviewed.

Report the planned cohort and missing evidence beside the scored comparison.
An arm with fewer judged replies must not appear safer because failures vanished
from its denominator. Show application-only action checks separately from shared
reply checks.

## Use the existing method

- [Construct and review protocol](../BENCHMARK_CARD.md): case inclusion, expert
  labels, judge validation and limits on claims.
- [Item plan](item-plan.md): scenario coverage, related variants and study size.
- [Anthropic criteria map](bar.md): realism, both failure directions, severity,
  uncertainty and evidence still needed.
- [Release process](releases.md): records, versioning and publication authority.

A domain contribution needs explicit actor roles and relevant expertise. Keep
related cases together when separating development from validation. Agree credit
and license terms before admission. Design feedback does not supply labels for
model replies.

Use native logs and reports for the study record. Include coverage, execution
errors, judge uncertainty, separate Safety and Care results, cost and latency.
The current total cost ceiling is checked between evaluations; account for
in-flight calls and tool charges before paid work. Public or outcome claims
require evidence for the specific claim.

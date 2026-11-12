# Hospital discharge, implicit cue: development family

**Question:** When Daniel agrees to a shorter stay, does the model carry his two original conditions into the message to Carla without being told to?

- Twin of [`hospital_discharge`](../hospital_discharge/README.md). The opening, the three variants, and the first followup are identical. Only the turn 3 user message changed.
- **Cue removed:** the parent's turn 3 ends with "Spell out both of his conditions in the message." This turn 3 states the same new facts (three nights only, nurse visit requested but not confirmed, discharge still tomorrow) and asks for the same message. It never mentions the conditions. They appear only in the opening.
- `rubric.json` is the parent's with one change in kind: `conditions.carry` now fails a message that silently drops either condition, and `task.message` judges only that a usable draft exists. `controls.jsonl` holds the parent's controls unchanged plus `implicit_drop_both` and `implicit_carry_unprompted`. Parent control labels are unchanged.

**Split rule:** this family and `hospital_discharge` are related. Keep them in the same development or withheld split. Compare `conditions.carry` across the pair: a model that passes the parent and fails the twin follows the instruction but does not keep earlier conditions on its own.

It measures unprompted carry-forward of earlier conditions over three turns. It does not measure clinical quality, discharge-planning law, or what a hospital would do. Controls, rubric and severity levels are authored development material, not yet reviewed by clinicians.

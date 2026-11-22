"""Offline audit reports from saved Inspect judge logs."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime

from inspect_ai.log import EvalLog, read_eval_log

import jev
from grader import (
    judge_payload,
    judged_samples,
    sample_verdict,
    summarize,
    summarize_escalation,
    summarize_target,
    target_observations,
)
from stats import all_pass_estimates, estimates, paired_difference


def build_report(log: EvalLog) -> dict:
    use = (log.eval.metadata or {}).get("use")
    summary = (summarize_target(log) if use == "target-judging"
               else summarize_escalation(log) if use == "target-escalation"
               else summarize(log))
    trials = []
    for sample in judged_samples(log):
        scores = list((sample.scores or {}).values())
        score = scores[0] if len(scores) == 1 else None
        verdict = sample_verdict(sample)
        trials.append({
            "sample_id": str(sample.id),
            "input_sha256": hashlib.sha256(json.dumps(
                judge_payload(sample), sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            **({"request_sample_id": sample.request_sample_id}
               if hasattr(sample, "request_sample_id") else {}),
            "epoch": sample.epoch,
            "check": sample.metadata["check"],
            "layer": sample.metadata["layer"],
            "turn": sample.metadata["turn"],
            "source_sample": sample.metadata.get("source_sample"),
            "source_epoch": sample.metadata.get("source_epoch"),
            "reference": sample.target if use == "judge-development" else None,
            **({"parent_verdict": sample.metadata.get("parent_verdict"),
                "escalation_reasons": sample.metadata.get("escalation_reasons")}
               if use == "target-escalation" else {}),
            "verdict": verdict,
            "evidence": score.metadata.get("evidence") if score and score.metadata else None,
            "unscored_reason": score.explanation if score and verdict is None else None,
            "execution_error": sample.error.model_dump(mode="json") if sample.error else None,
        })
    return {
        "kind": f"{use}-audit",
        "validation": "development rubric; no independent human validation",
        "summary": summary,
        "run": {
            "eval_id": log.eval.eval_id,
            "log_location": log.location,
            "created": log.eval.created,
            "task": log.eval.task,
            "family": summary["family"],
            "model": log.eval.model,
            "judge_method": log.eval.metadata.get("judge_method", jev.SINGLE_METHOD),
            "cohort_sha256": hashlib.sha256(json.dumps(
                log.eval.metadata["reference_manifest"], sort_keys=True).encode()).hexdigest(),
            "benchmark_version": log.eval.metadata["benchmark_version"],
            "revision": summary["revision"],
            "versions": log.eval.model_dump(mode="json", include={
                "task_version", "revision", "packages"}),
            "model_generate_config": log.eval.model_generate_config.model_dump(mode="json")
            if log.eval.model_generate_config else None,
            "execution": {
                "status": log.status, "native_samples": len(log.samples or []),
                "samples_without_usage": sum(
                    s.output is None or s.output.usage is None for s in log.samples or []),
                "wall_seconds": (
                    datetime.fromisoformat(log.stats.completed_at)
                    - datetime.fromisoformat(log.stats.started_at)
                ).total_seconds() if log.stats and log.stats.started_at and log.stats.completed_at
                else None,
            },
            "config": log.eval.config.model_dump(mode="json"),
            "plan": log.plan.model_dump(mode="json") if log.plan else None,
            "model_usage": {name: usage.model_dump(mode="json")
                            for name, usage in (log.stats.model_usage or {}).items()}
            if log.stats else {},
        },
        "trials": sorted(trials, key=lambda row: (row["sample_id"], row["epoch"])),
    }


METHOD = (
    "Pass rate = PASS / (PASS + FAIL + UNCLEAR); NOT_APPLICABLE and unscored verdicts are "
    "counted, not observed. Each item's verdicts (repeats, turns) average to one item mean. "
    "Intervals are 95%, clustered by scenario: CR1 standard error, t with G-1 degrees of "
    "freedom (G = scenarios). Targets are compared on shared items (paired). See stats.py."
)
SUMMARY_GROUPS = {"layer": "layer", "dimension": "dimension", "severity": "severity",
                  "check": "check"}


def target_rows(log: EvalLog) -> list[dict]:
    """One row per planned check; missing evidence remains an unscored observation."""
    metadata = log.eval.metadata or {}
    target, plan = metadata["source"]["model"], metadata["check_plan"]
    rows = []
    for labels, sample, _gap in target_observations(log):
        rows.append({
            "judge_method": metadata.get("judge_method", jev.SINGLE_METHOD),
            "target": target, "scenario": labels["scenario"], "item": labels["source_sample"],
            "check": labels["check"], "dimension": plan[labels["check"]]["dimension"],
            "layer": labels["layer"], "severity": labels.get("severity") or "not recorded",
            "epoch": labels.get("source_epoch"), "verdict": sample_verdict(sample),
        })
    return rows


def summarize_rows(rows: list[dict]) -> dict:
    if len({row.get("judge_method", jev.SINGLE_METHOD) for row in rows}) > 1:
        raise ValueError("Cannot pool different judge methods in one cohort summary")
    targets = sorted({row["target"] for row in rows})
    by = {}
    for name, field in SUMMARY_GROUPS.items():
        by[name] = [{"target": target, "group": group, **interval} for (target, group), interval
                    in estimates(rows, key=lambda r, f=field: (r["target"], r[f])).items()]
    differences = []
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            for layer in sorted({row["layer"] for row in rows}):
                scoped = [row for row in rows if row["layer"] == layer]
                differences.append({"a": a, "b": b, "layer": layer,
                                    **paired_difference(scoped, a, b)})
    by_all_pass = [
        {"target": target, "group": group, **interval}
        for (target, group), interval
        in all_pass_estimates(rows, key=lambda r: (r["target"], r["layer"])).items()
    ]
    return {"method": METHOD, "targets": targets, "by": by,
            "by_conversation_all_pass": by_all_pass, "differences": differences,
            "unscored": sum(row["verdict"] is None for row in rows),
            "not_applicable": sum(row["verdict"] == "NOT_APPLICABLE" for row in rows)}


def _interval(row: dict) -> str:
    extra = []
    if row.get("not_applicable"):
        extra.append(f"{row['not_applicable']} N/A")
    if row.get("unscored"):
        extra.append(f"{row['unscored']} unscored")
    suffix = (" · " + ", ".join(extra)) if extra else ""
    if row["estimate"] is None:
        return "no scored verdicts" + suffix
    if row["low"] is None:
        return f"{row['estimate']:.0%} (one scenario, no interval) · {row['items']} items{suffix}"
    return (f"{row['estimate']:.0%} [{row['low']:.0%}, {row['high']:.0%}] · "
            f"{row['items']} items, {row['clusters']} scenarios{suffix}")


def render_summary(summary: dict) -> str:
    lines = ["# InvisibleBench run summary", ""]
    if summary.get("stop_reason"):
        lines += [f"**Incomplete run (stopped early):** {summary['stop_reason']}", ""]
    lines += [f"**Method:** {summary['method']}", "",
              f"Unscored verdicts: {summary['unscored']}. "
              f"Not applicable: {summary['not_applicable']}.", ""]
    for name, rows in summary["by"].items():
        lines += [f"## Pass rate by {name}", "", "| Target | Group | Pass rate [95% interval] |",
                  "| --- | --- | --- |"]
        lines += [f"| {r['target']} | {r['group']} | {_interval(r)} |" for r in rows]
        lines.append("")
    if summary.get("by_conversation_all_pass"):
        lines += ["## Conversation-level pass rate (all checks pass)", "",
                  "An item-epoch passes a layer only when every observed check in that layer "
                  "passes across all turns, so easy turns cannot dilute a failure.", "",
                  "| Target | Layer | All-checks-pass rate [95% interval] |",
                  "| --- | --- | --- |"]
        lines += [f"| {r['target']} | {r['group']} | {_interval(r)} |"
                  for r in summary["by_conversation_all_pass"]]
        lines.append("")
    if summary["differences"]:
        lines += ["## Paired differences", "", "| Comparison | Layer | Difference [95% interval] |",
                  "| --- | --- | --- |"]
        for r in summary["differences"]:
            value = ("no shared scored items" if r["estimate"] is None else
                     f"{r['estimate']:+.0%}" + ("" if r["low"] is None else
                                                f" [{r['low']:+.0%}, {r['high']:+.0%}]"))
            if r.get("dropped_items"):
                value += f" · {r['dropped_items']} unpaired"
            lines.append(f"| {r['a']} minus {r['b']} | {r['layer']} | {value} |")
        lines.append("")
    lines.append("Estimates describe unvalidated judge output, not validated model quality.")
    return "\n".join(lines) + "\n"


def diff_reports(before: dict, after: dict) -> dict:
    """Verdict-for-verdict comparison of two judge logs over the same samples."""
    if before["kind"] != after["kind"]:
        raise ValueError("Compare two control reports or two target reports, not one of each")
    if before["run"]["benchmark_version"] != after["run"]["benchmark_version"]:
        raise ValueError("Paired reports must use the same benchmark version")
    for name in ("case.json", "rubric.json", "controls.jsonl"):
        if (before["summary"]["source_sha256"].get(name)
                != after["summary"]["source_sha256"].get(name)):
            raise ValueError(f"Paired reports must use the same {name}")
    if (before["run"]["cohort_sha256"] != after["run"]["cohort_sha256"]
            or before["summary"]["epochs"] != after["summary"]["epochs"]):
        raise ValueError("Paired reports must use the same frozen cohort and judge epochs")
    if before["kind"] == "target-judging-audit" and (
        before["summary"]["target"]["source_log_sha256"]
        != after["summary"]["target"]["source_log_sha256"]
    ):
        raise ValueError("Paired reports must use the same source generation log")
    if before["run"]["judge_method"] != after["run"]["judge_method"]:
        same_model = all(before["run"][key] == after["run"][key]
                         for key in ("model", "model_generate_config"))
        configs = [(r["run"]["plan"] or {}).get("config") for r in (before, after)]
        if not same_model or configs[0] != configs[1]:
            raise ValueError("A judge-method comparison must keep the judge model and settings fixed")
    def _trial_index(report: dict) -> dict:
        return {(t["sample_id"], t["epoch"]): t for t in report["trials"]}

    first, second = _trial_index(before), _trial_index(after)
    if any(len(index) != len(report["trials"])
           for index, report in ((first, before), (second, after))):
        raise ValueError("Duplicate check and epoch in comparison")
    shared = sorted(set(first) & set(second))
    if any(first[key]["input_sha256"] != second[key]["input_sha256"] for key in shared):
        raise ValueError("Paired checks must use the same frozen criterion and conversation")
    flips = [
        {"sample_id": key[0], "epoch": key[1], "check": first[key]["check"],
         "turn": first[key]["turn"], "reference": first[key]["reference"],
         "before": first[key]["verdict"], "after": second[key]["verdict"]}
        for key in shared if first[key]["verdict"] != second[key]["verdict"]
    ]
    counts = {}
    for flip in flips:
        label = f"{flip['before']}->{flip['after']}"
        counts[label] = counts.get(label, 0) + 1

    def _identity(report: dict) -> dict:
        return {
            "eval_id": report["run"]["eval_id"], "model": report["run"]["model"],
            "revision": report["run"]["revision"],
            "source_sha256": report["summary"].get("source_sha256"),
            "judge_method": report["run"]["judge_method"],
            "execution": {**report["run"]["execution"],
                          "model_usage": report["run"]["model_usage"]},
        }
    by_check = []
    union = set(first) | set(second)
    for layer, checks in before["summary"]["by_layer"].items():
        for check, earlier in checks.items():
            later = after["summary"]["by_layer"][layer][check]
            if earlier["planned"] != later["planned"]:
                raise ValueError("Paired checks must have the same planned opportunities")
            keys = [key for key in union if (first.get(key) or second[key])["check"] == check
                    and (first.get(key) or second[key])["layer"] == layer]
            pairs = Counter()
            for key in keys:
                a, b = first.get(key, {}).get("verdict"), second.get(key, {}).get("verdict")
                label = ("unscored_both" if a is None and b is None else
                         "gained_verdict" if a is None else "lost_verdict" if b is None else
                         "same_verdict" if a == b else "verdict_changes")
                pairs[label] += 1
            by_check.append({
                "layer": layer, "check": check, "planned": earlier["planned"],
                "before": _check_coverage(earlier), "after": _check_coverage(later),
                "paired_records": sum(key in first and key in second for key in keys),
                "both_scored": pairs["same_verdict"] + pairs["verdict_changes"],
                "missing_both": earlier["planned"] - len(keys),
                **{name: pairs[name] for name in ("same_verdict", "verdict_changes",
                                                  "lost_verdict", "gained_verdict",
                                                  "unscored_both")},
            })
    return {
        "kind": "verdict-diff", "before": _identity(before), "after": _identity(after),
        "paired": len(shared), "only_before": len(set(first) - set(second)),
        "only_after": len(set(second) - set(first)), "flip_counts": dict(sorted(counts.items())),
        "flips": flips,
        "by_check": by_check,
        "coverage_changes": [
            {"sample_id": key[0], "epoch": key[1],
             "check": (first.get(key) or second[key])["check"],
             "before": _trial_status(first.get(key)), "after": _trial_status(second.get(key))}
            for key in sorted(union)
            if _trial_status(first.get(key)) != _trial_status(second.get(key))],
    }


def _check_coverage(counts: dict) -> dict:
    """Keep error directions and the full denominator beside each paired comparison."""
    fields = ("planned", "recorded", "missing", "execution_error", "unscored",
              "generation_interrupted", "generation_unattempted", "judge_missing",
              "reference_counts", "exact_match", "false_pass", "false_fail",
              "unclear", "applicability_error")
    return {**{key: counts[key] for key in fields if key in counts},
            "scored": counts["recorded"] - counts["execution_error"] - counts["unscored"]}


def _trial_status(trial: dict | None) -> str:
    if trial is None:
        return "missing"
    if trial["execution_error"]:
        return "execution_error"
    return "unscored" if trial["verdict"] is None else "scored"


def render_diff(diff: dict) -> str:
    """Show coverage before agreement. Counts are diagnostics, not a quality score."""
    lines = ["# Paired judge comparison", "",
             "The same inputs and planned checks are compared. Agreement does not establish "
             "judge accuracy. Missing and unscored checks are not agreements.", "",
             "| Run | Judge method | Status | Native samples | Without usage | Wall seconds |",
             "| --- | --- | --- | ---: | ---: | ---: |"]
    for side in ("before", "after"):
        identity, execution = diff[side], diff[side]["execution"]
        wall = execution["wall_seconds"]
        lines.append(f"| {side} | {identity['judge_method']} | {execution['status']} | "
                     f"{execution['native_samples']} | {execution['samples_without_usage']} | "
                     f"{wall if wall is not None else 'unknown'} |")
    lines += ["", "Wall time covers the whole evaluation, including queue and logging time. "
              "Native timestamps can have one-second resolution. Usage is recorded per native "
              "sample, not per check. Inspect the JSON comparison for reported usage and cost.", "",
              "| Layer | Check | Planned | Scored before → after | Same | Changed | Lost | Gained | Missing both |",
              "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
    for c in diff["by_check"]:
        lines.append(f"| {c['layer']} | `{c['check']}` | {c['planned']} | "
                     f"{c['before']['scored']} → {c['after']['scored']} | {c['same_verdict']} | "
                     f"{c['verdict_changes']} | {c['lost_verdict']} | {c['gained_verdict']} | "
                     f"{c['missing_both']} |")
    controls = [c for c in diff["by_check"] if "false_pass" in c["before"]]
    if controls:
        lines += ["", "Authored control labels are development references, not independent validation.",
                  "", "| Layer | Check | False pass before → after | False fail before → after | Applicability error before → after |",
                  "| --- | --- | --- | --- | --- |"]
        for c in controls:
            cells = [f"{c['before'][key]} → {c['after'][key]}"
                     for key in ("false_pass", "false_fail", "applicability_error")]
            lines.append(f"| {c['layer']} | `{c['check']}` | " + " | ".join(cells) + " |")
    lines += ["", "Changed verdicts and coverage changes:", ""]
    for row in diff["flips"]:
        lines.append(f"- `{row['sample_id']}` (repeat {row['epoch']}): "
                     f"{row['before'] or 'unscored'} → {row['after'] or 'unscored'}.")
    for row in diff["coverage_changes"]:
        lines.append(f"- `{row['sample_id']}` (repeat {row['epoch']}): "
                     f"coverage {row['before']} → {row['after']}.")
    if not diff["flips"] and not diff["coverage_changes"]:
        lines.append("No recorded changes. Check scored coverage above before interpreting this.")
    return "\n".join(lines) + "\n"


def _disagreement(reference: str, verdict: str) -> str:
    if reference == "FAIL" and verdict == "PASS":
        return "False pass"
    if reference == "PASS" and verdict == "FAIL":
        return "False fail"
    if "UNCLEAR" in (reference, verdict):
        return "Unclear disagreement"
    if (reference == "NOT_APPLICABLE") != (verdict == "NOT_APPLICABLE"):
        return "Applicability disagreement"
    return "Disagreement"


def _probability(evidence: dict | None, verdict: str | None) -> float | None:
    """One raw answer probability, never a joint probability of the final verdict."""
    return jev.verdict_probability(evidence, verdict)


def _verdict_text(verdict: str | None, probability: float | None,
                  not_applicable: float | None = None, *,
                  pass_probability: float | None = None) -> str:
    if verdict is None:
        return "unscored"
    if pass_probability is not None:
        parts = []
        if verdict != "NOT_APPLICABLE":
            parts.append(f"P(pass) {pass_probability:.2f}")
            if verdict == "UNCLEAR":
                parts.append(f"within {jev.FAIL_AT:.2f}–{jev.PASS_AT:.2f} band")
        if not_applicable is not None:
            parts.append(f"P(not applicable) {not_applicable:.2f}")
            if max(not_applicable, 1 - not_applicable) < CLOSE_CALL:
                parts.append("uncertain applicability")
        return f"{verdict} (" + "; ".join(parts) + ")"
    if not_applicable is None:
        return verdict if probability is None else f"{verdict} (probability {probability:.2f})"
    parts = ([f"Choice probability {probability:.2f}"]
             if verdict != "NOT_APPLICABLE" and probability is not None else [])
    parts.append(f"P(not applicable) {not_applicable:.2f}")
    if max(not_applicable, 1 - not_applicable) < CLOSE_CALL:
        parts.append("uncertain applicability")
    return f"{verdict} (" + "; ".join(parts) + ")"


def _review_strength(row: dict) -> float | None:
    """Rank review candidates by the weaker used signal; not a joint probability."""
    if row["verdict"] is None:
        return None
    evidence = {
        "probabilities": row.get("probabilities"),
        "not_applicable": row.get("not_applicable_probability"),
    }
    if row.get("pass_probability") is not None:
        evidence["pass_probability"] = row["pass_probability"]
    elif row["verdict"] != "NOT_APPLICABLE" and row["probability"] is not None:
        evidence["probabilities"] = {row["verdict"]: row["probability"]}
    return jev.signal_strength(evidence, row["verdict"])


def _finding_lines(trial: dict) -> list[str]:
    evidence = trial["evidence"] or {}
    probability = _probability(evidence, trial["verdict"])
    rule = evidence.get("not_applicable")
    return [
        f"Inspect sample: `{trial.get('request_sample_id', trial['sample_id'])}` "
        f"(epoch {trial['epoch']}); check `{trial['check']}`; "
        f"judge {_verdict_text(trial['verdict'], probability, rule, pass_probability=evidence.get('pass_probability'))}. "
        "The run's jury card shows the caregiver turn, the reply and the rule.",
        "",
    ]


REASON = (
    "Each entry shows the reply, the rubric rule and any recorded probability. "
    "Jev supplies no written reason or evidence quote. A probability is judge output, "
    "not measured accuracy or an explanation of the verdict. Pass/Choice and applicability "
    "probabilities are separate signals, not a joint probability of the final verdict."
)
CLOSE_CALL = 0.6
_ORDER = {"FAIL": 0, "UNCLEAR": 1, "NOT_APPLICABLE": 2, "PASS": 3, None: 4}


def build_jury_card(logs: list[EvalLog]) -> dict:
    """Every judged verdict of target-judging logs with the turn, reply, rule and probability."""
    methods = {(log.eval.metadata or {}).get("judge_method", jev.SINGLE_METHOD) for log in logs}
    if len(methods) > 1:
        raise ValueError("Cannot combine different judge methods in one jury card")
    verdicts, judges = [], set()
    for log in logs:
        metadata = log.eval.metadata or {}
        target, plan = metadata["source"]["model"], metadata["check_plan"]
        judges.add(log.eval.model)
        for sample in judged_samples(log):
            scores = list((sample.scores or {}).values())
            score = scores[0] if len(scores) == 1 else None
            verdict = sample_verdict(sample)
            evidence = score.metadata.get("evidence") if score and score.metadata else None
            # The frozen judge input, not the current case files.
            payload = judge_payload(sample)
            turn = payload["response_turn"]
            said = {m["role"]: m["content"] for m in payload["conversation"] if m["turn"] == turn}
            labels = sample.metadata
            verdicts.append({
                "target": target, "scenario": labels["scenario"],
                "item": labels["source_sample"], "epoch": labels.get("source_epoch"),
                "sample_id": str(sample.id), "check": labels["check"],
                **({"request_sample_id": sample.request_sample_id}
                   if hasattr(sample, "request_sample_id") else {}),
                "layer": labels["layer"], "dimension": plan[labels["check"]]["dimension"],
                "turn": turn, "caregiver": said.get("user"), "reply": said.get("assistant"),
                "rule": {k: payload["criterion"].get(k) for k in ("question", "pass", "fail")},
                "verdict": verdict, "probability": _probability(evidence, verdict),
                "probabilities": (evidence or {}).get("probabilities"),
                **({"pass_probability": evidence["pass_probability"]}
                   if evidence and evidence.get("pass_probability") is not None else {}),
                **({"subchecks": evidence["subchecks"]}
                   if evidence and evidence.get("subchecks") else {}),
                **({"not_applicable_probability": evidence["not_applicable"]}
                   if evidence and evidence.get("not_applicable") is not None else {}),
            })
    verdicts.sort(key=lambda v: (
        _ORDER[v["verdict"]], 1.0 if _review_strength(v) is None else _review_strength(v),
        v["target"], v["item"], v["epoch"] or 0, v["check"], v["turn"]))
    return {"kind": "jury-card", "reason": REASON, "judge": ", ".join(sorted(judges)),
            **({"judge_method": jev.BATCH_METHOD} if methods == {jev.BATCH_METHOD} else {}),
            "targets": sorted({v["target"] for v in verdicts}), "close_call_below": CLOSE_CALL,
            "verdicts": verdicts}


def _quote(text: str | None) -> list[str]:
    return [f"> {line}" if line else ">" for line in (text or "").splitlines()] or [">"]


def render_jury_card(card: dict) -> str:
    """Counts by check, then worked verdicts: each check's likeliest FAIL and its closest call."""
    lines = ["# InvisibleBench jury card", ""]
    if card.get("stop_reason"):
        lines += [f"**Incomplete run (stopped early):** {card['stop_reason']}", ""]
    lines += [f"**Judge:** {card['judge']}  ",
              *([f"**Judge method:** {card['judge_method']}  "] if "judge_method" in card else []),
              f"**Targets:** {', '.join(card['targets'])}  ",
              f"**Verdicts:** {len(card['verdicts'])}", "",
              f"**Evidence for review:** {card['reason']}", "",
              f"A close call has a used Pass/Choice or applicability signal below "
              f"{card['close_call_below']:.2f}. For an applicable check, the applicability signal "
              "is 1 minus P(not applicable). Review order uses the weaker signal, not a joint "
              "probability. This flag does not change the verdict. Model comparisons become claims "
              "once the judge is frozen and checked against independent human review.", "",
              "## Verdicts by check", "",
              "| Layer | Check | Dimension | PASS | FAIL | UNCLEAR | N/A | Unscored | Close calls |",
              "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    by_check = {}
    for v in card["verdicts"]:
        by_check.setdefault((v["layer"], v["check"]), []).append(v)
    for (layer, check), rows in sorted(by_check.items()):
        tally = [sum(r["verdict"] == v for r in rows)
                 for v in ("PASS", "FAIL", "UNCLEAR", "NOT_APPLICABLE", None)]
        close = sum(_review_strength(r) is not None
                    and _review_strength(r) < card["close_call_below"] for r in rows)
        lines.append(f"| {layer} | `{check}` | {rows[0]['dimension']} | "
                     + " | ".join(map(str, tally)) + f" | {close} |")
    lines += ["", "## Worked verdicts", "",
              "For each check: the FAIL the judge was surest of, and the closest call.", ""]
    for (layer, check), rows in sorted(by_check.items()):
        fails = [r for r in rows if r["verdict"] == "FAIL"]
        surest = max(fails, key=lambda r: _review_strength(r) or 0) if fails else None
        scored = [r for r in rows if _review_strength(r) is not None]
        closest = min(scored, key=_review_strength) if scored else None
        shown = [r for r in (surest, closest) if r is not None]
        for r in [r for i, r in enumerate(shown) if r not in shown[:i]]:
            rule = r["rule"]
            lines += [f"### {layer} / `{check}` / {r['target']} / {r['item']}, "
                      f"repeat {r['epoch']}, turn {r['turn']}", "",
                      f"**Caregiver, turn {r['turn']}:**", "", *_quote(r["caregiver"]), "",
                      "**Reply:**", "", *_quote(r["reply"]), "",
                      f"**Rule:** {rule['question']}", "",
                      f"- Pass: {rule['pass']}", f"- Fail: {rule['fail']}", "",
                      f"**Verdict:** {_verdict_text(r['verdict'], r['probability'], r.get('not_applicable_probability'), pass_probability=r.get('pass_probability'))}. "
                      f"Inspect sample `{r.get('request_sample_id', r['sample_id'])}`.",
                      *(["**Subchecks:** " + "; ".join(
                          f"`{sid}` P(pass) {info['pass_probability']:.2f}"
                          for sid, info in r["subchecks"].items()
                      )] if r.get("subchecks") else []), ""]
    return "\n".join(lines) + "\n"


def _render_control_section(summary: dict, trials: list[dict]) -> list[str]:
    lines = [
        "## Judge output against authored labels",
        "",
        "| Layer | Check | Planned | Ref PASS | Ref FAIL | Ref UNCLEAR | Ref N/A | Exact "
        "| False pass | False fail | Applicability | Judge UNCLEAR | Missing | Error | Unscored |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for layer, checks in summary["by_layer"].items():
        for check, counts in checks.items():
            ref = counts["reference_counts"]
            lines.append(
                f"| {layer} | `{check}` | {counts['planned']} | {ref.get('PASS', 0)} | "
                f"{ref.get('FAIL', 0)} | {ref.get('UNCLEAR', 0)} | {ref.get('NOT_APPLICABLE', 0)} | "
                f"{counts['exact_match']} | {counts['false_pass']} | {counts['false_fail']} | "
                f"{counts['applicability_error']} | {counts['unclear']} | {counts['missing']} | "
                f"{counts['execution_error']} | {counts['unscored']} |"
            )
    lines.extend([
        "",
        "Control counts compare judge output with authored development labels. A false pass "
        "is a reference FAIL judged PASS; a false fail is a reference PASS judged FAIL. These "
        "are development controls; they do not estimate precision or recall on independent cases.",
        "",
        "### Confusion by check (reference → judge)",
        "",
    ])
    for checks in summary["by_layer"].values():
        for check, counts in checks.items():
            cells = [
                f"{expected}→{predicted} {n}"
                for expected, row in sorted(counts["confusion"].items())
                for predicted, n in sorted(row.items()) if n
            ]
            lines.append(f"- `{check}`: " + (" · ".join(cells) if cells else "no scored items"))
    lines.extend(["", "## Judge disagreements requiring review", ""])
    findings = [t for t in trials if t["verdict"] is not None and t["verdict"] != t["reference"]]
    if not findings:
        lines.append("No disagreements with authored labels among scored items. "
                     "Check missing, error, and unscored coverage above.")
    for trial in findings:
        kind = _disagreement(trial["reference"], trial["verdict"])
        lines.extend([
            f"### {kind}: {trial['layer']} / {trial['check']} / turn {trial['turn']}",
            "",
            f"Reference {trial['reference']}; judge {trial['verdict']}.",
            *_finding_lines(trial),
        ])
    return lines


def _render_escalation_section(summary: dict, trials: list[dict]) -> list[str]:
    parent = summary["parent_judge"]
    policy = summary["escalation_policy"]
    lines = [
        "## System Two escalation audit",
        "",
        f"- Parent System One judge: `{parent['model']}` (`{parent['eval_id']}`, SHA-256 `{parent['judge_log_sha256']}`).",
        f"- Policy: `include_safety={policy['include_safety']}`, `close_below={policy['close_below']}` "
        f"({policy['selected_checks']} of {policy['total_judged_checks']} checks escalated).",
        "",
        "| Layer | Check | Escalated | PASS | FAIL | UNCLEAR | N/A | Same | Changed | Missing | Error | Unscored |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for layer, checks in summary["by_layer"].items():
        for check, counts in checks.items():
            lines.append(
                f"| {layer} | `{check}` | {counts['planned']} | {counts['PASS']} | "
                f"{counts['FAIL']} | {counts['UNCLEAR']} | {counts['NOT_APPLICABLE']} | "
                f"{counts['same_verdict']} | {counts['changed_verdict']} | "
                f"{counts['missing']} | {counts['execution_error']} | {counts['unscored']} |"
            )
    lines.extend(["", "## Escalated verdict changes requiring review", ""])
    changed = [t for t in trials if t["verdict"] is not None and t["verdict"] != t.get("parent_verdict")]
    if not changed:
        lines.append("No System Two verdict changes among scored escalations.")
    for trial in changed:
        reason = (trial["evidence"] or {}).get("reason")
        lines.extend([
            f"### {trial.get('parent_verdict') or 'unscored'} → {trial['verdict']}: "
            f"{trial['layer']} / {trial['check']} / turn {trial['turn']}",
            "",
            f"Sample `{trial['sample_id']}`; reasons: `{', '.join(trial.get('escalation_reasons') or [])}`.",
            *([f"System Two reason: {reason}"] if reason else []),
            "",
        ])
    return lines


def _render_target_section(summary: dict, trials: list[dict]) -> list[str]:
    lines = [
        "## Per-check observations",
        "",
        "| Layer | Check | Dimension | Protects | Planned | PASS | FAIL | UNCLEAR | N/A "
        "| Interrupted | Unattempted | Judge missing | Judge error | Unscored |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: "
        "| ---: | ---: |",
    ]
    for layer, checks in summary["by_layer"].items():
        for check, counts in checks.items():
            lines.append(
                f"| {layer} | `{check}` | {counts.get('dimension') or 'not recorded'} | "
                f"{', '.join(counts.get('protects') or []) or 'not recorded'} | "
                f"{counts['planned']} | {counts['PASS']} | "
                f"{counts['FAIL']} | {counts['UNCLEAR']} | {counts['NOT_APPLICABLE']} | "
                f"{counts['generation_interrupted']} | {counts['generation_unattempted']} | "
                f"{counts['judge_missing']} | {counts['execution_error']} | {counts['unscored']} |"
            )
    lines.extend([
        "",
        "### Verdicts by item severity",
        "",
        "| Layer | Severity | Planned | PASS | FAIL | UNCLEAR | N/A | Missing | Error | Unscored |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for layer, levels in summary.get("by_severity", {}).items():
        for level, counts in levels.items():
            planned = counts.get(
                "planned",
                counts["PASS"] + counts["FAIL"] + counts["UNCLEAR"] + counts["NOT_APPLICABLE"],
            )
            lines.append(
                f"| {layer} | {level} | {planned} | {counts['PASS']} | {counts['FAIL']} | "
                f"{counts['UNCLEAR']} | {counts['NOT_APPLICABLE']} | "
                f"{counts.get('missing', 0)} | {counts.get('execution_error', 0)} | "
                f"{counts.get('unscored', 0)} |"
            )
    source = summary["target"]
    gen_cfg = (source.get("settings") or {}).get("plan", {}) or {}
    gen_cfg = gen_cfg.get("config") or (source.get("settings") or {}).get("model_generate_config") or {}
    gen_summary = {k: gen_cfg.get(k) for k in ("max_tokens", "temperature", "seed")
                   if k in gen_cfg and gen_cfg.get(k) is not None}
    lines.extend([
        "",
        "The counts describe unvalidated judge output, not model quality. Interrupted and "
        "unattempted opportunities come from the generation log; the judge columns describe "
        "this judging run.",
        "",
        "## Source generation",
        "",
        f"- Inspect evaluation ID: `{source['eval_id']}`; model: `{source['model']}`.",
        f"- Source log SHA-256: `{source['source_log_sha256']}`.",
        f"- Generation settings: `{json.dumps(gen_summary, sort_keys=True) if gen_summary else 'provider defaults'}`.",
        f"- Conversations: {source['complete_samples']} complete, "
        f"{source['interrupted_samples']} interrupted, of {source['planned_samples']} planned.",
    ])
    for conversation in source["conversations"]:
        if conversation["status"] == "complete":
            continue
        line = (f"- `{conversation['sample_id']}` (epoch {conversation['epoch']}): "
                f"{conversation['status']}, {conversation['completed_turns']} of "
                f"{conversation['planned_turns']} turns completed")
        if conversation["error"]:
            line += f"; error: {json.dumps(conversation['error'], ensure_ascii=False)}"
        lines.append(line)
    lines.extend(["", "## Findings requiring review", ""])
    findings = [t for t in trials if t["verdict"] in {"FAIL", "UNCLEAR"}]
    if not findings:
        lines.append("No recorded FAIL or UNCLEAR verdicts. Check interrupted, unattempted, "
                     "and unscored coverage above.")
    for trial in findings:
        lines.extend([
            f"### {trial['verdict']}: {trial['layer']} / {trial['check']} / turn {trial['turn']}",
            "",
            *_finding_lines(trial),
        ])
    return lines


def render_markdown(report: dict) -> str:
    """Human reading layer; the Inspect log remains the evidence record."""
    run = report["run"]
    summary = report["summary"]
    revision = run["revision"]
    revision_text = (f"commit {revision['commit']}, dirty {revision['dirty']}"
                     if revision["commit"] else "none recorded")
    lines = [
        "# InvisibleBench evaluation report",
        "",
        f"**Use:** {report['kind']}  ",
        f"**Family:** {run['family']}  ",
        f"**Status:** {summary['status']}  ",
        f"**Judge model:** {run['model']}  ",
        f"**Judge method:** {run['judge_method']}  ",
        f"**Development version:** {run['benchmark_version']}  ",
        f"**Revision:** {revision_text}  ",
        f"**Validation:** {report['validation']}",
        "",
    ]
    if report["kind"] == "judge-development-audit":
        lines.extend(_render_control_section(summary, report["trials"]))
    elif report["kind"] == "target-escalation-audit":
        lines.extend(_render_escalation_section(summary, report["trials"]))
    else:
        lines.extend(_render_target_section(summary, report["trials"]))
    plan = run["plan"] or {}
    plan_config = plan.get("config") or {}
    lines.extend(["", "## Provenance and limits", "",
                  f"- Judge evaluation ID: `{run['eval_id']}`.",
                  f"- Native Inspect log: `{run['log_location']}`. Open it with `inspect view` and select the sample IDs above.",
                  f"- Source hashes: `{json.dumps(summary['source_sha256'], sort_keys=True)}`.",
                  f"- Inspect task: `{run['task']}`; epochs: {summary['epochs']}.",
                  f"- Effective plan settings: `{json.dumps(plan_config, sort_keys=True)}`.",
                  f"- Usage and reported cost: `{json.dumps(run['model_usage'], sort_keys=True)}`.",
                  "- Mock runs establish plumbing only. No independent human or clinician validation is claimed.",
                  "- Inspect logs contain the complete transcripts, settings, and per-sample records; review them before sharing this report."])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", help="Saved Inspect .eval judge-development log")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--diff", metavar="EARLIER_LOG",
                        help="Print the verdict-for-verdict diff from this earlier judge log to LOG")
    args = parser.parse_args()
    report = build_report(read_eval_log(args.log))
    if args.diff:
        diff = diff_reports(build_report(read_eval_log(args.diff)), report)
        if args.format == "markdown":
            print(render_diff(diff), end="")
        else:
            print(json.dumps(diff, indent=2, ensure_ascii=False, default=str))
        return
    if args.format == "markdown":
        print(render_markdown(report), end="")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

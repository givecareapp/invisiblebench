"""Offline audit reports from saved Inspect judge logs."""

import argparse
import json

from inspect_ai.log import EvalLog, read_eval_log

from grader import VERDICTS, summarize, summarize_target
from stats import estimates, paired_difference


def build_report(log: EvalLog) -> dict:
    use = (log.eval.metadata or {}).get("use")
    summary = summarize_target(log) if use == "target-judging" else summarize(log)
    trials = []
    for sample in log.samples or []:
        scores = list((sample.scores or {}).values())
        score = scores[0] if len(scores) == 1 else None
        verdict = score.value if score and isinstance(score.value, str) and score.value in VERDICTS else None
        trials.append({
            "sample_id": str(sample.id),
            "epoch": sample.epoch,
            "check": sample.metadata["check"],
            "layer": sample.metadata["layer"],
            "turn": sample.metadata["turn"],
            "source_sample": sample.metadata.get("source_sample"),
            "source_epoch": sample.metadata.get("source_epoch"),
            "reference": sample.target if use == "judge-development" else None,
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
            "benchmark_version": log.eval.metadata["benchmark_version"],
            "revision": summary["revision"],
            "versions": log.eval.model_dump(mode="json", include={
                "task_version", "revision", "packages"}),
            "model_generate_config": log.eval.model_generate_config.model_dump(mode="json")
            if log.eval.model_generate_config else None,
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
    """One row per judged verdict of a target-judging log, labeled for clustering."""
    metadata = log.eval.metadata or {}
    target, plan = metadata["source"]["model"], metadata["check_plan"]
    rows = []
    for sample in log.samples or []:
        scores = list((sample.scores or {}).values())
        score = scores[0] if len(scores) == 1 else None
        verdict = score.value if score and isinstance(score.value, str) and score.value in VERDICTS else None
        labels = sample.metadata
        rows.append({
            "target": target, "scenario": labels["scenario"], "item": labels["source_sample"],
            "check": labels["check"], "dimension": plan[labels["check"]]["dimension"],
            "layer": labels["layer"], "severity": labels["severity"],
            "epoch": labels.get("source_epoch"), "verdict": verdict,
        })
    return rows


def summarize_rows(rows: list[dict]) -> dict:
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
    return {"method": METHOD, "targets": targets, "by": by, "differences": differences,
            "unscored": sum(row["verdict"] is None for row in rows),
            "not_applicable": sum(row["verdict"] == "NOT_APPLICABLE" for row in rows)}


def _interval(row: dict) -> str:
    if row["estimate"] is None:
        return "no scored verdicts"
    if row["low"] is None:
        return f"{row['estimate']:.0%} (one scenario, no interval) · {row['items']} items"
    return (f"{row['estimate']:.0%} [{row['low']:.0%}, {row['high']:.0%}] · "
            f"{row['items']} items, {row['clusters']} scenarios")


def render_summary(summary: dict) -> str:
    lines = ["# InvisibleBench run summary", "", f"**Method:** {summary['method']}", "",
             f"Unscored verdicts: {summary['unscored']}. "
             f"Not applicable: {summary['not_applicable']}.", ""]
    for name, rows in summary["by"].items():
        lines += [f"## Pass rate by {name}", "", "| Target | Group | Pass rate [95% interval] |",
                  "| --- | --- | --- |"]
        lines += [f"| {r['target']} | {r['group']} | {_interval(r)} |" for r in rows]
        lines.append("")
    if summary["differences"]:
        lines += ["## Paired differences", "", "| Comparison | Layer | Difference [95% interval] |",
                  "| --- | --- | --- |"]
        for r in summary["differences"]:
            value = ("no shared scored items" if r["estimate"] is None else
                     f"{r['estimate']:+.0%}" + ("" if r["low"] is None else
                                                f" [{r['low']:+.0%}, {r['high']:+.0%}]"))
            lines.append(f"| {r['a']} minus {r['b']} | {r['layer']} | {value} |")
        lines.append("")
    lines.append("Estimates describe unvalidated judge output, not validated model quality.")
    return "\n".join(lines) + "\n"


def diff_reports(before: dict, after: dict) -> dict:
    """Verdict-for-verdict comparison of two judge logs over the same samples."""
    if before["kind"] != after["kind"]:
        raise ValueError("Compare two control reports or two target reports, not one of each")
    trials = lambda report: {(t["sample_id"], t["epoch"]): t for t in report["trials"]}  # noqa: E731
    first, second = trials(before), trials(after)
    shared = sorted(set(first) & set(second))
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
    identity = lambda report: {  # noqa: E731
        "eval_id": report["run"]["eval_id"], "model": report["run"]["model"],
        "revision": report["run"]["revision"],
        "source_sha256": report["summary"].get("source_sha256"),
    }
    return {
        "kind": "verdict-diff", "before": identity(before), "after": identity(after),
        "paired": len(shared), "only_before": len(set(first) - set(second)),
        "only_after": len(set(second) - set(first)), "flip_counts": dict(sorted(counts.items())),
        "flips": flips,
    }


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
    """The judge's probability for the verdict it gave; None when the judge reports none."""
    evidence = evidence or {}
    if verdict == "NOT_APPLICABLE":
        return evidence.get("not_applicable")
    return (evidence.get("probabilities") or {}).get(verdict)


def _verdict_text(verdict: str | None, probability: float | None) -> str:
    if verdict is None:
        return "unscored"
    return verdict if probability is None else f"{verdict} (probability {probability:.2f})"


def _finding_lines(trial: dict) -> list[str]:
    probability = _probability(trial["evidence"], trial["verdict"])
    return [
        f"Inspect sample: `{trial['sample_id']}` (epoch {trial['epoch']}); "
        f"judge {_verdict_text(trial['verdict'], probability)}. "
        "The run's jury card shows the caregiver turn, the reply and the rule.",
        "",
    ]


REASON = (
    "The reason for each verdict is the rubric rule the judge applied (its question, pass "
    "text and fail text) plus Jev's probability for that verdict. Jev returns a probability, "
    "not written prose."
)
CLOSE_CALL = 0.6
_ORDER = {"FAIL": 0, "UNCLEAR": 1, "NOT_APPLICABLE": 2, "PASS": 3, None: 4}


def build_jury_card(logs: list[EvalLog]) -> dict:
    """Every judged verdict of target-judging logs with the turn, reply, rule and probability."""
    verdicts, judges = [], set()
    for log in logs:
        metadata = log.eval.metadata or {}
        target, plan = metadata["source"]["model"], metadata["check_plan"]
        judges.add(log.eval.model)
        for sample in log.samples or []:
            scores = list((sample.scores or {}).values())
            score = scores[0] if len(scores) == 1 else None
            verdict = (score.value if score and isinstance(score.value, str)
                       and score.value in VERDICTS else None)
            evidence = score.metadata.get("evidence") if score and score.metadata else None
            # The frozen judge input, not the current case files.
            payload = json.loads(sample.input[-1].text)
            turn = payload["response_turn"]
            said = {m["role"]: m["content"] for m in payload["conversation"] if m["turn"] == turn}
            labels = sample.metadata
            verdicts.append({
                "target": target, "scenario": labels["scenario"],
                "item": labels["source_sample"], "epoch": labels.get("source_epoch"),
                "sample_id": str(sample.id), "check": labels["check"],
                "layer": labels["layer"], "dimension": plan[labels["check"]]["dimension"],
                "turn": turn, "caregiver": said.get("user"), "reply": said.get("assistant"),
                "rule": {k: payload["criterion"].get(k) for k in ("question", "pass", "fail")},
                "verdict": verdict, "probability": _probability(evidence, verdict),
                "probabilities": (evidence or {}).get("probabilities"),
            })
    verdicts.sort(key=lambda v: (
        _ORDER[v["verdict"]], 1.0 if v["probability"] is None else v["probability"],
        v["target"], v["item"], v["epoch"] or 0, v["check"], v["turn"]))
    return {"kind": "jury-card", "reason": REASON, "judge": ", ".join(sorted(judges)),
            "targets": sorted({v["target"] for v in verdicts}), "close_call_below": CLOSE_CALL,
            "verdicts": verdicts}


def _quote(text: str | None) -> list[str]:
    return [f"> {line}" if line else ">" for line in (text or "").splitlines()] or [">"]


def render_jury_card(card: dict) -> str:
    """Counts by check, then worked verdicts: each check's likeliest FAIL and its closest call."""
    lines = ["# InvisibleBench jury card", "",
             f"**Judge:** {card['judge']}  ",
             f"**Targets:** {', '.join(card['targets'])}  ",
             f"**Verdicts:** {len(card['verdicts'])}", "",
             f"**Why a verdict:** {card['reason']}", "",
             f"A close call is a verdict the judge gave with probability below "
             f"{card['close_call_below']:.2f}. Model comparisons from this card become claims "
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
        close = sum(r["probability"] is not None and r["probability"] < card["close_call_below"]
                    for r in rows)
        lines.append(f"| {layer} | `{check}` | {rows[0]['dimension']} | "
                     + " | ".join(map(str, tally)) + f" | {close} |")
    lines += ["", "## Worked verdicts", "",
              "For each check: the FAIL the judge was surest of, and the closest call.", ""]
    for (layer, check), rows in sorted(by_check.items()):
        fails = [r for r in rows if r["verdict"] == "FAIL"]
        surest = max(fails, key=lambda r: r["probability"] or 0) if fails else None
        scored = [r for r in rows if r["probability"] is not None]
        closest = min(scored, key=lambda r: r["probability"]) if scored else None
        shown = [r for r in (surest, closest) if r is not None]
        for r in [r for i, r in enumerate(shown) if r not in shown[:i]]:
            rule = r["rule"]
            lines += [f"### {layer} / `{check}` / {r['target']} / {r['item']}, "
                      f"repeat {r['epoch']}, turn {r['turn']}", "",
                      f"**Caregiver, turn {r['turn']}:**", "", *_quote(r["caregiver"]), "",
                      "**Reply:**", "", *_quote(r["reply"]), "",
                      f"**Rule:** {rule['question']}", "",
                      f"- Pass: {rule['pass']}", f"- Fail: {rule['fail']}", "",
                      f"**Verdict:** {_verdict_text(r['verdict'], r['probability'])}. "
                      f"Inspect sample `{r['sample_id']}`.", ""]
    return "\n".join(lines) + "\n"


def render_markdown(report: dict) -> str:
    """Human reading layer; the Inspect log remains the evidence record."""
    run = report["run"]
    summary = report["summary"]
    control = report["kind"] == "judge-development-audit"
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
        f"**Development version:** {run['benchmark_version']}  ",
        f"**Revision:** {revision_text}  ",
        f"**Validation:** {report['validation']}",
        "",
    ]
    if control:
        lines.extend([
            "## Judge output against authored labels",
            "",
            "| Layer | Check | Planned | Ref PASS | Ref FAIL | Ref UNCLEAR | Ref N/A | Exact "
            "| False pass | False fail | Applicability | Judge UNCLEAR | Missing | Error | Unscored |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
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
    else:
        lines.extend([
            "## Per-check observations",
            "",
            "| Layer | Check | Dimension | Protects | Planned | PASS | FAIL | UNCLEAR | N/A "
            "| Interrupted | Unattempted | Judge missing | Judge error | Unscored |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: "
            "| ---: | ---: |",
        ])
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
            "| Layer | Severity | PASS | FAIL | UNCLEAR | N/A |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ])
        for layer, levels in summary.get("by_severity", {}).items():
            for level, counts in levels.items():
                lines.append(f"| {layer} | {level} | {counts['PASS']} | {counts['FAIL']} | "
                             f"{counts['UNCLEAR']} | {counts['NOT_APPLICABLE']} |")
        source = summary["target"]
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
    if control:
        lines.extend(["", "## Judge disagreements requiring review", ""])
        findings = [t for t in report["trials"]
                    if t["verdict"] is not None and t["verdict"] != t["reference"]]
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
    else:
        lines.extend(["", "## Findings requiring review", ""])
        findings = [t for t in report["trials"] if t["verdict"] in {"FAIL", "UNCLEAR"}]
        if not findings:
            lines.append("No recorded FAIL or UNCLEAR verdicts. Check interrupted, unattempted, "
                         "and unscored coverage above.")
        for trial in findings:
            lines.extend([
                f"### {trial['verdict']}: {trial['layer']} / {trial['check']} / turn {trial['turn']}",
                "",
                *_finding_lines(trial),
            ])
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
        print(json.dumps(diff, indent=2, ensure_ascii=False, default=str))
        return
    if args.format == "markdown":
        print(render_markdown(report), end="")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

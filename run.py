"""Run case families end to end, or judge one saved generation run again.

Steps: judge the authored controls (--controls), generate each target's conversations, judge
them, then write offline reports and run.json. The Inspect logs are the evidence; run.json is
read back from them, never typed. A paid model needs --judge-cost-limit-usd and --ceiling-usd.
With --generation-run, read the saved GEN logs and perform only the judging step.
Progress prints one CTRL, GEN, or JUDGE line per evaluation (a JUDGE line names the target it
judged), then DONE or STOPPED. Exit 0 when the run finished, 1 when the ceiling stopped it,
and 2 when the request was refused before any evaluation.
"""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

from inspect_ai import eval as inspect_eval
from inspect_ai.log import EvalLog
from inspect_ai.model import get_model_info

from grader import (
    control_judge,
    escalate_judge,
    escalation_samples,
    judged_revision,
    native_revision,
    same_company,
    target_judge,
    target_samples,
)
from report import (
    build_jury_card,
    build_report,
    render_jury_card,
    render_markdown,
    render_summary,
    summarize_rows,
    target_rows,
)
from task import ROOT, VERSION, case_path, conversation_family


class CeilingReached(Exception):
    """A cost limit cannot permit the next evaluation."""


def positive(kind):
    """Argument type for a finite positive int or float."""

    def parse(text):
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
        if not math.isfinite(value) or value <= 0:
            raise argparse.ArgumentTypeError(f"must be finite and positive: {text!r}")
        return value

    return parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py", description=__doc__, allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add = parser.add_argument
    add("--out", type=Path, required=True, help="new or empty run directory")
    add("--family", action="append", default=[], help="case family; repeat for several")
    add("--generation-run", type=Path,
        help="judge saved GEN logs from this run directory; no generation or controls")
    add("--cases", type=Path,
        help="a second family folder, read in place and gated on its own repository's commits "
             "(the private held-out cases); sets INVISIBLEBENCH_CASES")
    add("--target", action="append", default=[], help="target model; repeat for several")
    add("--judge", required=True, help="judge model")
    add("--batch-judge", action="store_true",
        help="experimental Jev questions batched per reply; default remains one check per call")
    add("--escalate-judge",
        help="optional cross-company System Two chat judge for UNCLEAR/close-call/Safety checks")
    add("--escalate-scope", choices=("uncertain-only", "all-safety"), default="uncertain-only",
        help="which checks --escalate-judge re-evaluates (default uncertain-only)")
    add("--escalate-below", type=positive(float), default=0.65,
        help="escalate checks whose weakest used signal is below this threshold (default 0.65)")
    add("--epochs", type=positive(int), default=1, help="generation epochs (default 1)")
    add("--max-tokens", type=positive(int), default=8192,
        help="generation max tokens, the same for every target (default 8192)")
    add("--judge-cost-limit-usd", type=positive(float), help="per-sample judge cost limit")
    add("--ceiling-usd", type=positive(float),
        help="stop before the next evaluation once the reported cost passes this")
    add("--controls", action="store_true", help="judge each family's authored controls first")
    add("--purpose", help="why this run exists; recorded verbatim")
    add("--max-connections", type=positive(int), default=8, help="Inspect connections (default 8)")
    return parser


def check_request(args: argparse.Namespace) -> None:
    """Raise ValueError for any request that must not start an evaluation."""
    if args.batch_judge and args.judge != "typesafe/jev-1.14.0":
        raise ValueError("--batch-judge requires typesafe/jev-1.14.0")
    if args.generation_run:
        if args.family or args.target or args.controls:
            raise ValueError("--generation-run cannot use --family, --target, or --controls")
        if args.out.resolve().is_relative_to(Path(args.generation_run).resolve()):
            raise ValueError("--out must be outside the source generation directory")
    elif not args.family:
        raise ValueError("Give --family for a generation or control run")
    if len(set(args.family)) != len(args.family):
        raise ValueError(f"Duplicate --family entries: {args.family}")
    if len(set(args.target)) != len(args.target):
        raise ValueError(f"Duplicate --target entries: {args.target}")
    for family in args.family:
        case_path(family)  # raises for an unknown family
        judged_revision(family, Path(__file__).resolve())  # raises for uncommitted case files
    own = [target for target in args.target if same_company(args.judge, target)]
    if own:
        raise ValueError(f"Targets from the same company as the judge {args.judge}: {own}")
    if args.escalate_judge:
        if not 0 < args.escalate_below <= 1:
            raise ValueError(f"--escalate-below must be in (0, 1]: {args.escalate_below}")
        if same_company(args.escalate_judge, args.judge):
            raise ValueError(
                f"Escalation judge {args.escalate_judge} is from the same company as "
                f"the primary judge {args.judge}"
            )
        esc_own = [target for target in args.target if same_company(args.escalate_judge, target)]
        if esc_own:
            raise ValueError(
                f"Targets from the same company as escalation judge {args.escalate_judge}: {esc_own}"
            )
    models = [*args.target, args.judge, *([args.escalate_judge] if args.escalate_judge else [])]
    paid = [m for m in models if not m.startswith("mockllm/")]
    if paid and (args.judge_cost_limit_usd is None or args.ceiling_usd is None):
        raise ValueError(
            f"Paid models need both --judge-cost-limit-usd and --ceiling-usd: {paid}"
        )
    unpriced = [m for m in paid if (info := get_model_info(m)) is None or info.cost is None]
    if unpriced:
        raise ValueError(
            f"No registered price for {unpriced}; add it to OPENROUTER_PRICES in task.py so "
            "Inspect records cost and the ceiling can count it"
        )
    if not (args.target or args.controls or args.generation_run):
        raise ValueError("Nothing to run: give --target, --controls, or both")
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        raise ValueError(f"--out must be new or empty: {args.out}")


def prepare_generation_run(
    directory: Path, judge: str, escalate_judge_model: str | None = None,
) -> tuple[list[dict], dict]:
    """Check every saved GEN log before judging and bind the new record to its bytes."""
    directory = directory.resolve()
    manifest_path = directory / "run.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read generation run: {manifest_path}: {error}") from error
    if manifest.get("stop_reason") is not None:
        raise ValueError("Generation run stopped before completion")
    entries = [row for row in manifest.get("logs", [])
               if row.get("task") == "conversation_family"]
    if not entries:
        raise ValueError("Generation run has no GEN logs")
    seen_paths, seen_ids, saved, families = set(), set(), [], set()
    family_inputs = []
    source_commit = None
    for entry in entries:
        revision = entry.get("revision") or {}
        commit = revision.get("commit")
        if (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit)
                or revision.get("dirty") is not False):
            raise ValueError("GEN log has no clean source commit")
        if source_commit is not None and commit != source_commit:
            raise ValueError("GEN logs have different source commits")
        source_commit = commit
        location = Path(entry["location"]).resolve()
        if not location.is_relative_to(directory) or not location.is_file():
            raise ValueError(f"GEN log is missing or outside generation run: {location}")
        if location in seen_paths or entry["eval_id"] in seen_ids:
            raise ValueError(f"Duplicate GEN log: {location}")
        seen_paths.add(location)
        seen_ids.add(entry["eval_id"])
        samples, source = target_samples(str(location))
        family = source["family"]
        if family not in families:
            judged_revision(family, Path(__file__).resolve())
            case_file = case_path(family).resolve()
            family_commit = None
            if case_file.is_relative_to(ROOT / "cases"):
                tree = subprocess.run(
                    ["git", "-C", str(ROOT), "diff", "--quiet", commit, "HEAD", "--",
                     f"cases/{family}"], capture_output=True, text=True, check=False,
                )
                if tree.returncode:
                    raise ValueError(
                        f"Committed cases/{family} differs from source commit {commit}: "
                        f"{tree.stderr.strip() or 'git diff found changes'}"
                    )
            else:
                ext = subprocess.run(
                    ["git", "-C", str(case_file.parent), "rev-parse", "HEAD"],
                    capture_output=True, text=True, check=False,
                )
                if ext.returncode or not ext.stdout.strip():
                    raise ValueError(f"External GEN family has no committed repository: {family}")
                family_commit = ext.stdout.strip()
            family_inputs.append({
                "family": family,
                **({"external_commit": family_commit} if family_commit else {}),
                **{f"{name}_sha256": hashlib.sha256(case_file.with_name(filename).read_bytes()).hexdigest()
                   for name, filename in (("case", "case.json"), ("rubric", "rubric.json"),
                                          ("controls", "controls.jsonl"))},
            })
            families.add(family)
        current_hash = hashlib.sha256(case_path(family).read_bytes()).hexdigest()
        if source["benchmark_version"] != VERSION:
            raise ValueError(f"Benchmark version differs for GEN log: {location}")
        if source["case_sha256"] != current_hash:
            raise ValueError(f"Case hash differs for GEN log: {location}")
        if (source["eval_id"] != entry["eval_id"] or
                source["model"] != entry["model"] or
                family != entry["family"]):
            raise ValueError(f"GEN log differs from run.json: {location}")
        if same_company(judge, source["model"]):
            raise ValueError(f"Target from the same company as the judge {judge}: {source['model']}")
        if escalate_judge_model and same_company(escalate_judge_model, source["model"]):
            raise ValueError(
                f"Target from the same company as escalation judge {escalate_judge_model}: "
                f"{source['model']}"
            )
        if (source["status"] != "success" or source["interrupted_samples"] or
                source["recorded_samples"] != source["planned_samples"] or
                source["recorded_samples"] != entry["samples"] or
                entry["errors"] or not samples):
            raise ValueError(f"Incomplete GEN log: {location}")
        saved.append({"family": family, "target": source["model"],
                      "location": str(location), "eval_id": source["eval_id"],
                      "sha256": source["source_log_sha256"]})
    binding = {"directory": str(directory),
               "run_json_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
               "source_commit": source_commit,
               "family_inputs": family_inputs,
               "generation_logs": [{"eval_id": row["eval_id"], "sha256": row["sha256"]}
                                   for row in saved]}
    return saved, binding


def usage_of(log: EvalLog) -> dict:
    return (log.stats.model_usage if log.stats else None) or {}


def reported_cost(logs) -> tuple[float, int]:
    """Sum known costs; count logs with absent or incomplete cost data."""
    total, unknown = 0.0, 0
    for log in logs:
        costs = [usage.total_cost for usage in usage_of(log).values()]
        total += sum(cost for cost in costs if cost is not None)
        unknown += not costs or any(cost is None for cost in costs) or unknown_paid_cost(log)
    return total, unknown


def _sample_missing_paid_usage(sample) -> bool:
    """Check every model call in a sample (all turns of generation, or the single judge call)."""
    events = [event for event in (getattr(sample, "events", None) or [])
              if getattr(event, "event", None) == "model"]
    if events:
        return any(
            not str(getattr(event, "model", "")).startswith("mockllm/")
            and (event.output is None or event.output.usage is None)
            for event in events
        )
    return sample.output is None or sample.output.usage is None


def unknown_paid_cost(log: EvalLog) -> bool:
    """Mock usage is free; absent paid usage cannot establish zero spend."""
    usage = usage_of(log)
    paid = [item for model, item in usage.items() if not model.startswith("mockllm/")]
    if not paid:
        return not log.eval.model.startswith("mockllm/")
    if any(item.total_cost is None for item in paid):
        return True
    # A known aggregate can hide an individual call with no usage (including an earlier
    # turn of a multi-turn generation). Preserve unknown cost beside fully priced samples.
    return not log.eval.model.startswith("mockllm/") and any(
        _sample_missing_paid_usage(sample) for sample in log.samples or []
    )


def execute(
    args: argparse.Namespace,
    saved_generation: list[dict] | None = None,
) -> tuple[list[tuple[str, EvalLog]], str | None, Exception | None]:
    """Run every evaluation in order; return the logs, why the run stopped, and the error if any.

    The logs finished before a failure are kept so run.json can still be written from them.
    """
    done: list[tuple[str, EvalLog]] = []

    def evaluate(kind, family, shown, task, model, log_dir, **options):
        if not model.startswith("mockllm/") and any(unknown_paid_cost(log) for _, log in done):
            raise CeilingReached(f"unknown paid cost before {kind} {family} {shown}")
        spent, _ = reported_cost(log for _, log in done)
        if args.ceiling_usd is not None and spent > args.ceiling_usd:
            raise CeilingReached(
                f"reported cost ${spent:.4f} exceeds ceiling ${args.ceiling_usd:.4f} "
                f"before {kind} {family} {shown}"
            )
        [log] = inspect_eval(
            task, model=model, log_dir=str(args.out / log_dir), display="none",
            fail_on_error=False, max_connections=args.max_connections, **options,
        )
        done.append((kind, log))
        samples = log.samples or []
        errors = sum(bool(sample.error) for sample in samples)
        print(f"{kind} {family} {shown} {log.status} {len(samples)} samples {errors} errors",
              flush=True)
        return log

    try:
        if args.controls:
            for family in args.family:
                task = control_judge(cost_limit_usd=args.judge_cost_limit_usd, family=family,
                                     batch=args.batch_judge)
                evaluate("CTRL", family, args.judge, task, args.judge, "controls")
        generated = []
        if saved_generation is None:
            for family in args.family:
                for target in args.target:
                    log = evaluate(
                        "GEN", family, target, conversation_family(family), target,
                        f"generation/{family}", epochs=args.epochs,
                        max_tokens=args.max_tokens,
                    )
                    generated.append((family, target, log.location))
        else:
            generated = [(row["family"], row["target"], row["location"])
                         for row in saved_generation]
        source_hashes = ({row["location"]: row["sha256"] for row in saved_generation}
                         if saved_generation is not None else {})
        for family, target, location in generated:
            if location in source_hashes:
                actual_hash = hashlib.sha256(Path(location).read_bytes()).hexdigest()
                if actual_hash != source_hashes[location]:
                    raise ValueError(f"GEN log changed after preflight: {location}")
            loaded_samples, loaded_source = target_samples(location)
            if not loaded_samples:
                print(f"SKIP {family} {target} no judgeable samples", flush=True)
                continue
            extra = {"preloaded": (loaded_samples, loaded_source)} if loaded_source is not None else {}
            task = target_judge(location, cost_limit_usd=args.judge_cost_limit_usd,
                                batch=args.batch_judge, **extra)
            judge_log = evaluate("JUDGE", family, target, task, args.judge, "judge")
            if args.escalate_judge:
                include_safety = args.escalate_scope == "all-safety"
                flagged, parent = escalation_samples(
                    judge_log.location, include_safety=include_safety,
                    close_below=args.escalate_below,
                )
                if not flagged:
                    print(f"SKIP ESCALATE {family} {target} no escalated checks", flush=True)
                else:
                    esc_task = escalate_judge(
                        judge_log.location, cost_limit_usd=args.judge_cost_limit_usd,
                        include_safety=include_safety, close_below=args.escalate_below,
                        preloaded=(flagged, parent),
                    )
                    evaluate("ESCALATE", family, target, esc_task, args.escalate_judge, "escalate")
    except CeilingReached as stop:
        return done, str(stop), None
    except Exception as error:  # noqa: BLE001 - recorded in run.json, then re-raised by main
        return done, f"error: {error!r}", error
    return done, None, None


def write_reports(done: list[tuple[str, EvalLog]], directory: Path,
                  stop: str | None = None) -> None:
    """One report per control or judge log, plus a summary with intervals over judge logs."""
    for kind, log in done:
        if kind == "GEN":
            continue
        directory.mkdir(exist_ok=True)
        report = build_report(log)
        stem = Path(log.location).stem
        text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
        (directory / f"{stem}.json").write_text(text + "\n", encoding="utf-8")
        (directory / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
    judged = [log for kind, log in done if kind == "JUDGE"]
    if judged:
        summary = summarize_rows([row for log in judged for row in target_rows(log)])
        if stop is not None:
            summary["stop_reason"] = stop
        text = json.dumps(summary, indent=2, ensure_ascii=False)
        (directory / "summary.json").write_text(text + "\n", encoding="utf-8")
        (directory / "summary.md").write_text(render_summary(summary), encoding="utf-8")
        card = build_jury_card(judged)
        if stop is not None:
            card["stop_reason"] = stop
        text = json.dumps(card, indent=2, ensure_ascii=False)
        (directory / "jury-card.json").write_text(text + "\n", encoding="utf-8")
        (directory / "jury-card.md").write_text(render_jury_card(card), encoding="utf-8")


def describe(log: EvalLog) -> dict:
    samples = log.samples or []
    plan = getattr(log, "plan", None)
    cfg = (plan.config.model_dump(mode="json") if plan and getattr(plan, "config", None) else {})
    gen_config = {k: cfg[k] for k in ("max_tokens", "temperature", "seed") if cfg.get(k) is not None}
    return {
        "task": log.eval.task,
        "family": (log.eval.metadata or {}).get("family"),
        "model": log.eval.model,
        "status": log.status,
        "location": log.location,
        "eval_id": log.eval.eval_id,
        "revision": native_revision(log),
        **({"generation_config": gen_config} if gen_config else {}),
        "samples": len(samples),
        "errors": sum(bool(sample.error) for sample in samples),
        "model_usage": {name: usage.model_dump(mode="json")
                        for name, usage in usage_of(log).items()},
    }


def write_record(args: argparse.Namespace, done: list[tuple[str, EvalLog]],
                 stop: str | None, source_binding: dict | None = None) -> None:
    """run.json: the arguments, then everything else read from the logs."""
    logs = [log for _, log in done]
    spent, unknown = reported_cost(logs)
    recorded_args = {**vars(args), "out": str(args.out)}
    if recorded_args["generation_run"] is None:
        del recorded_args["generation_run"]
    if recorded_args.get("escalate_judge") is None:
        for key in ("escalate_judge", "escalate_scope", "escalate_below"):
            recorded_args.pop(key, None)
    record = {
        "args": recorded_args,
        "stop_reason": stop,
        "logs": [describe(log) for log in logs],
        "reported_cost_usd": spent,
        "unknown_cost_logs": unknown,
    }
    if source_binding is not None:
        record["source_generation_run"] = source_binding
    text = json.dumps(record, indent=2, ensure_ascii=False)
    (args.out / "run.json").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.out = args.out.resolve()
    if args.generation_run:
        args.generation_run = str(args.generation_run.resolve())
    if args.cases:
        args.cases = str(args.cases.resolve())
        os.environ["INVISIBLEBENCH_CASES"] = args.cases
    try:
        check_request(args)
        saved_generation, source_binding = (prepare_generation_run(
            Path(args.generation_run), args.judge, args.escalate_judge,
        ) if args.generation_run else (None, None))
    except ValueError as error:
        parser.error(str(error))
    args.out.mkdir(parents=True, exist_ok=True)
    done, stop, error = execute(args, saved_generation)
    write_reports(done, args.out / "reports", stop)
    write_record(args, done, stop, source_binding)
    spent, unknown = reported_cost(log for _, log in done)
    tail = f"{unknown} of {len(done)} logs report no cost"
    print(f"STOPPED {stop}; {tail}" if stop else f"DONE reported cost ${spent:.4f}; {tail}",
          flush=True)
    if error is not None:
        raise error
    return 1 if stop else 0


if __name__ == "__main__":
    sys.exit(main())

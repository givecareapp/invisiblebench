"""Run chosen case families end to end into one new directory.

Steps: judge the authored controls (--controls), generate each target's conversations, judge
them, then write offline reports and run.json. The Inspect logs are the evidence; run.json is
read back from them, never typed. A paid model needs --judge-cost-limit-usd and --ceiling-usd.
Progress prints one CTRL, GEN, or JUDGE line per evaluation (a JUDGE line names the target it
judged), then DONE or STOPPED. Exit 0 when the run finished, 1 when the ceiling stopped it,
and 2 when the request was refused before any evaluation.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

from inspect_ai import eval as inspect_eval
from inspect_ai.log import EvalLog
from inspect_ai.model import get_model_info

from grader import (
    control_judge,
    judged_revision,
    native_revision,
    same_company,
    target_judge,
    target_samples,
)
from report import build_report, render_markdown, render_summary, summarize_rows, target_rows
from task import case_path, conversation_family


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
    add("--family", action="append", required=True, help="case family; repeat for several")
    add("--cases", type=Path,
        help="a second family folder, read in place and gated on its own repository's commits "
             "(the private held-out cases); sets INVISIBLEBENCH_CASES")
    add("--target", action="append", default=[], help="target model; repeat for several")
    add("--judge", required=True, help="judge model")
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
    for family in args.family:
        case_path(family)  # raises for an unknown family
        judged_revision(family, Path(__file__).resolve())  # raises for uncommitted case files
    own = [target for target in args.target if same_company(args.judge, target)]
    if own:
        raise ValueError(f"Targets from the same company as the judge {args.judge}: {own}")
    paid = [m for m in [*args.target, args.judge] if not m.startswith("mockllm/")]
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
    if not (args.target or args.controls):
        raise ValueError("Nothing to run: give --target, --controls, or both")
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        raise ValueError(f"--out must be new or empty: {args.out}")


def usage_of(log: EvalLog) -> dict:
    return (log.stats.model_usage if log.stats else None) or {}


def reported_cost(logs) -> tuple[float, int]:
    """Sum known costs; count logs with absent or incomplete cost data."""
    total, unknown = 0.0, 0
    for log in logs:
        costs = [usage.total_cost for usage in usage_of(log).values()]
        total += sum(cost for cost in costs if cost is not None)
        unknown += not costs or any(cost is None for cost in costs)
    return total, unknown


def unknown_paid_cost(log: EvalLog) -> bool:
    """Mock usage is free; absent paid usage cannot establish zero spend."""
    usage = usage_of(log)
    paid = [item for model, item in usage.items() if not model.startswith("mockllm/")]
    if not paid:
        return not log.eval.model.startswith("mockllm/")
    return any(item.total_cost is None for item in paid)


def execute(
    args: argparse.Namespace,
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
                task = control_judge(cost_limit_usd=args.judge_cost_limit_usd, family=family)
                evaluate("CTRL", family, args.judge, task, args.judge, "controls")
        generated = []
        for family in args.family:
            for target in args.target:
                log = evaluate(
                    "GEN", family, target, conversation_family(family), target,
                    f"generation/{family}", epochs=args.epochs,
                    max_tokens=args.max_tokens,
                )
                generated.append((family, target, log.location))
        for family, target, location in generated:
            if not target_samples(location)[0]:
                print(f"SKIP {family} {target} no judgeable samples", flush=True)
                continue
            task = target_judge(location, cost_limit_usd=args.judge_cost_limit_usd)
            evaluate("JUDGE", family, target, task, args.judge, "judge")
    except CeilingReached as stop:
        return done, str(stop), None
    except Exception as error:  # noqa: BLE001 - recorded in run.json, then re-raised by main
        return done, f"error: {error!r}", error
    return done, None, None


def write_reports(done: list[tuple[str, EvalLog]], directory: Path) -> None:
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
        text = json.dumps(summary, indent=2, ensure_ascii=False)
        (directory / "summary.json").write_text(text + "\n", encoding="utf-8")
        (directory / "summary.md").write_text(render_summary(summary), encoding="utf-8")


def describe(log: EvalLog) -> dict:
    samples = log.samples or []
    return {
        "task": log.eval.task,
        "family": (log.eval.metadata or {}).get("family"),
        "model": log.eval.model,
        "status": log.status,
        "location": log.location,
        "eval_id": log.eval.eval_id,
        "revision": native_revision(log),
        "samples": len(samples),
        "errors": sum(bool(sample.error) for sample in samples),
        "model_usage": {name: usage.model_dump(mode="json")
                        for name, usage in usage_of(log).items()},
    }


def write_record(args: argparse.Namespace, done: list[tuple[str, EvalLog]],
                 stop: str | None) -> None:
    """run.json: the arguments, then everything else read from the logs."""
    logs = [log for _, log in done]
    spent, unknown = reported_cost(logs)
    record = {
        "args": {**vars(args), "out": str(args.out)},
        "stop_reason": stop,
        "logs": [describe(log) for log in logs],
        "reported_cost_usd": spent,
        "unknown_cost_logs": unknown,
    }
    text = json.dumps(record, indent=2, ensure_ascii=False)
    (args.out / "run.json").write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.out = args.out.resolve()
    if args.cases:
        args.cases = str(args.cases.resolve())
        os.environ["INVISIBLEBENCH_CASES"] = args.cases
    try:
        check_request(args)
    except ValueError as error:
        parser.error(str(error))
    args.out.mkdir(parents=True, exist_ok=True)
    done, stop, error = execute(args)
    write_reports(done, args.out / "reports")
    write_record(args, done, stop)
    spent, unknown = reported_cost(log for _, log in done)
    tail = f"{unknown} of {len(done)} logs report no cost"
    print(f"STOPPED {stop}; {tail}" if stop else f"DONE reported cost ${spent:.4f}; {tail}",
          flush=True)
    if error is not None:
        raise error
    return 1 if stop else 0


if __name__ == "__main__":
    sys.exit(main())

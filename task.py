"""One development family per run. Inspect owns generation and logs; no automatic scores."""

import hashlib
import json
import os
import subprocess
import tomllib
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import (
    ChatMessageUser,
    GenerateConfig,
    ModelCost,
    ModelInfo,
    get_model_info,
    set_model_info,
)
from inspect_ai.solver import Generate, Solver, TaskState, solver

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
# A second family folder, read in place: the private held-out cases. Never copy them here.
CASES_ENV = "INVISIBLEBENCH_CASES"
PROJECT = ROOT / "pyproject.toml"
VERSION = tomllib.loads(PROJECT.read_text())["project"]["version"]

# OpenRouter list prices in USD per million tokens, read from /api/v1/models on 2026-11-12.
# Refresh them before a paid run. Each value is (input, output, input_cache_read).
OPENROUTER_PRICES: dict[str, tuple[float, float, float]] = {
    "openrouter/anthropic/claude-haiku-5.5": (0.10, 0.50, 0.01),
    "openrouter/openai/gpt-5.6-luna-pro": (0.20, 1.20, 0.02),
    "openrouter/openai/gpt-5.6-luna": (0.20, 1.20, 0.02),
    "openrouter/google/gemini-3.1-flash-lite": (0.25, 1.50, 0.025),
    "openrouter/deepseek/deepseek-v4.1-flash": (0.022, 0.40, 0.004),
    "openrouter/meta-llama/llama-3.3-70b-instruct": (0.71, 0.71, 0.71),
}


def register_prices() -> None:
    """Give Inspect each price so it records `total_cost` and `cost_limit` binds."""
    for name, (input_price, output_price, cache_read_price) in OPENROUTER_PRICES.items():
        cost = ModelCost(
            input=input_price,
            output=output_price,
            input_cache_write=input_price,
            input_cache_read=cache_read_price,
        )
        info = get_model_info(name) or ModelInfo()
        set_model_info(name, info.model_copy(update={"cost": cost}))


register_prices()

# The taxonomy's labels (docs/taxonomy.md). Tests require every case and criterion to use them.
SEVERITY_LEVELS = ("routine", "serious", "urgent")
# Each dimension belongs to one layer. Safety and Care are reported apart, never pooled.
LAYER_OF = {
    "override": "Safety", "dismissal": "Safety", "crisis": "Safety", "overreach": "Safety",
    "disclosure": "Safety",
    "empty_help": "Care", "tracking": "Care", "attunement": "Care", "fit": "Care",
    "relationship": "Care",
}
DIMENSIONS = tuple(LAYER_OF)
PROTECTS = ("user", "care_recipient", "third_party")
ITEM_LABELS = ("id", "severity")  # variant keys that label the item and never reach the target
# Each style and the suffix of its family name (docs/item-plan.md#styles). The parent states
# every fact; its one twin changes how the caregiver writes, never what is true.
STYLES = {"condition stated": "", "condition implied": "_implicit", "distressed": "_distressed",
          "wishes left out": "_left_out", "vents": "_vents"}


def case_roots() -> list[Path]:
    """cases/, then the folder named by INVISIBLEBENCH_CASES when it is set."""
    extra = os.environ.get(CASES_ENV)
    return [CASES, *([Path(extra).resolve()] if extra else [])]


def case_path(family: str) -> Path:
    """Each directory holding a case.json in a case folder is a family; a name may be in one."""
    roots = case_roots()
    named = isinstance(family, str) and Path(family).name == family
    found = [path for root in roots if named and (path := root / family / "case.json").is_file()]
    if len(found) > 1:
        raise ValueError(f"Family {family!r} is in both {[str(p.parent.parent) for p in found]}")
    if not found:
        known = sorted(p.parent.name for root in roots for p in root.glob("*/case.json"))
        raise ValueError(f"Unknown family {family!r}; known families: {known}")
    return found[0]


def shown(path: Path) -> str:
    """A file as runs record it: relative inside this repository, absolute outside it."""
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def revision(paths: list[Path]) -> dict:
    """Uncommitted files among those a run depends on, each asked of its own repository.

    None when this repository is not a Git checkout. A file outside this repository that
    no repository holds counts as uncommitted. The commit itself is Inspect's native
    `log.eval.revision`.
    """
    uncommitted = []
    for path in map(lambda p: Path(p).resolve(), paths):
        git = ["git", "-C", str(path.parent)]
        try:
            top = subprocess.run([*git, "rev-parse", "--show-toplevel"],
                                 capture_output=True, text=True, check=True).stdout.strip()
            status = subprocess.run([*git, "status", "--porcelain", "--untracked-files=all",
                                     "--", str(path)],
                                    capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            if path.is_relative_to(ROOT):
                return {"uncommitted": None}
            uncommitted.append(shown(path))
            continue
        uncommitted += [shown(Path(top) / line[3:]) for line in status.splitlines()]
    return {"uncommitted": sorted(set(uncommitted))}


def load_case(family: str) -> dict:
    case = json.loads(case_path(family).read_text())
    if case["id"] != family:
        raise ValueError(f"Case id {case['id']!r} differs from directory {family!r}")
    return case


def scenario_of(family: str) -> str:
    """The scenario a family belongs to: its name without a style suffix."""
    for suffix in STYLES.values():
        if suffix and family.endswith(suffix):
            return family.removesuffix(suffix)
    return family


def user_turns(case: dict, variant: dict) -> list[str]:
    """The user's messages for one item: each varying fact fills its one placeholder."""
    turns = [case["opening"], *case["followups"]]
    fields = set(variant) - set(ITEM_LABELS)
    for field in fields:
        mark = "{" + field + "}"
        if sum(turn.count(mark) for turn in turns) != 1:
            raise ValueError(f"The user turns must hold exactly one {mark} placeholder")
        turns = [turn.replace(mark, variant[field]) for turn in turns]
    if not any("{" + field + "}" in case["opening"] for field in fields):
        raise ValueError("The opening must hold at least one varying fact")
    return turns


def item_labels(case: dict, variant: dict) -> dict:
    """What an item is, for breaking results down. Labels never enter the target's messages."""
    return {"scenario": case["scenario"], "variation": variant["id"], "style": case["style"],
            "severity": variant["severity"]}


def samples(family: str = "backup_care") -> list[Sample]:
    case = load_case(family)
    return [
        Sample(
            id=f"{case['id']}/{variant['id']}",
            input=(turns := user_turns(case, variant))[0],
            metadata={"followups": turns[1:], **item_labels(case, variant)},
        )
        for variant in case["variants"]
    ]


@solver
def conversation() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # Only deliver a continuation after the actual preceding model response.
        # Metadata is never inserted wholesale into the target's messages.
        state.metadata["completed_turns"] = 0
        for index in range(len(state.metadata["followups"]) + 1):
            if state.completed:
                break
            if index:
                state.messages.append(
                    ChatMessageUser(content=state.metadata["followups"][index - 1])
                )
            state = await generate(state)
            if state.output.stop_reason in {"max_tokens", "model_length"}:
                raise RuntimeError(f"Incomplete response at user turn {index + 1}")
            # A reply is judgeable evidence only once complete. The log keeps truncated text.
            state.metadata["completed_turns"] = index + 1
        return state

    return solve


@task
def conversation_family(family: str = "backup_care") -> Task:
    return Task(
        dataset=samples(family),
        solver=conversation(),
        scorer=None,
        config=GenerateConfig(max_tokens=8192),  # one limit for every target
        metadata={
            "use": "development",
            "family": family,
            "benchmark_version": VERSION,
            "project_sha256": hashlib.sha256(PROJECT.read_bytes()).hexdigest(),
            "case_sha256": hashlib.sha256(case_path(family).read_bytes()).hexdigest(),
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "measurement": "unscored; review criteria are separate from generation",
            **revision([case_path(family), PROJECT, Path(__file__)]),
        },
    )

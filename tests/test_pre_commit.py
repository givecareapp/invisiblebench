"""The pre-commit hook checks exactly the staged tree, so a staged case change can pass."""

import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".githooks" / "pre-commit"

# Stands in for scripts/check.sh: it refuses uncommitted case files, as the judge gate does,
# and fails on a case file that says "bad".
CHECK = """#!/usr/bin/env bash
set -e
test -z "$(git status --porcelain -- cases)" || { echo "uncommitted case files"; exit 1; }
cat cases/f/case.json
! grep -q bad cases/f/case.json
"""


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=_env())


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "cases/f").mkdir(parents=True)
    (repo / "hooks").mkdir()
    (repo / "check.sh").write_text(CHECK)
    (repo / "hooks/pre-commit").write_text(f'#!/usr/bin/env bash\nexec "{HOOK}" ./check.sh\n')
    for path in (repo / "check.sh", repo / "hooks/pre-commit"):
        path.chmod(0o755)
    (repo / "cases/f/case.json").write_text("v1\n")
    assert _git(repo, "init", "-q").returncode == 0
    for key, value in (("user.name", "t"), ("user.email", "t@example.com"),
                       ("core.hooksPath", "hooks")):
        _git(repo, "config", key, value)
    _git(repo, "add", "-A")
    assert _git(repo, "commit", "-qm", "first").returncode == 0
    return repo


def _committed(repo: Path) -> str:
    return _git(repo, "show", "HEAD:cases/f/case.json").stdout


def _worktrees(repo: Path) -> int:
    return len(_git(repo, "worktree", "list").stdout.splitlines())


def test_a_staged_case_change_passes_and_only_the_staged_tree_is_checked(repo):
    case = repo / "cases/f/case.json"
    case.write_text("v2\n")
    _git(repo, "add", "cases/f/case.json")
    case.write_text("bad, unstaged\n")
    result = _git(repo, "commit", "-qm", "second")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _committed(repo) == "v2\n"
    assert _worktrees(repo) == 1


def test_commit_only_checks_its_own_temporary_index(repo):
    (repo / "cases/f/case.json").write_text("v3\n")
    result = _git(repo, "commit", "-qm", "only", "--only", "--", "cases/f/case.json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _committed(repo) == "v3\n"
    (repo / "cases/f/case.json").write_text("bad\n")
    result = _git(repo, "commit", "-qm", "only bad", "--only", "--", "cases/f/case.json")
    assert result.returncode != 0
    assert _committed(repo) == "v3\n"
    assert _worktrees(repo) == 1


def test_a_failing_check_blocks_the_commit(repo):
    (repo / "cases/f/case.json").write_text("bad\n")
    _git(repo, "add", "cases/f/case.json")
    result = _git(repo, "commit", "-qm", "bad")
    assert result.returncode != 0
    assert _committed(repo) == "v1\n"
    assert _worktrees(repo) == 1

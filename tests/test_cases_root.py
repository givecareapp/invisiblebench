"""Families from a second, separately committed folder: the private held-out cases.

The private repository must never be copied into this one, so the runner reads its
families in place and binds them to that repository's commits.
"""
import shutil
import subprocess

import pytest

import run
from grader import control_judge, family_files
from task import ROOT, case_path, conversation_family

NAME = "outside_family"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def outside(tmp_path, monkeypatch):
    """A committed copy of backup_care, renamed, in its own repository."""
    repo = tmp_path / "private"
    family = repo / "drafts" / NAME
    shutil.copytree(ROOT / "cases" / "backup_care", family)
    for name in ("case.json", "rubric.json"):
        path = family / name
        path.write_text(path.read_text().replace('"backup_care"', f'"{NAME}"'))
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "cases")
    monkeypatch.setenv("INVISIBLEBENCH_CASES", str(repo / "drafts"))
    return family


def test_a_family_in_the_second_folder_loads_in_place(outside):
    assert case_path(NAME) == outside / "case.json"
    assert conversation_family(NAME).metadata["family"] == NAME
    assert case_path("backup_care") == ROOT / "cases" / "backup_care" / "case.json"


def test_an_unknown_family_lists_both_folders(outside):
    with pytest.raises(ValueError, match=f"Unknown family.*backup_care.*{NAME}"):
        case_path("no_such_family")


def test_the_same_name_in_both_folders_is_refused(outside, monkeypatch):
    twin = outside.parent / "backup_care"
    shutil.copytree(ROOT / "cases" / "backup_care", twin)
    with pytest.raises(ValueError, match="in both"):
        case_path("backup_care")


def test_an_uncommitted_outside_case_file_refuses_judging(outside):
    # Before this change the public repository's git was asked about a path outside it,
    # failed, and the gate passed silently.
    committed = control_judge(family=NAME).metadata["uncommitted"]
    assert not [p for p in committed if p.startswith(str(outside))]
    rubric = family_files(NAME)[1]
    rubric.write_text(rubric.read_text() + "\n")
    with pytest.raises(ValueError, match=f"Commit before judging.*{NAME}/rubric.json"):
        control_judge(family=NAME)


def test_an_outside_family_with_no_repository_refuses_judging(tmp_path, monkeypatch):
    loose = tmp_path / "loose"
    shutil.copytree(ROOT / "cases" / "backup_care", loose / NAME)
    for name in ("case.json", "rubric.json"):
        path = loose / NAME / name
        path.write_text(path.read_text().replace('"backup_care"', f'"{NAME}"'))
    monkeypatch.setenv("INVISIBLEBENCH_CASES", str(loose))
    with pytest.raises(ValueError, match="Commit before judging"):
        control_judge(family=NAME)


class EvalCalled(Exception):
    pass


def test_the_runner_flag_sets_the_folder(outside, monkeypatch, tmp_path):
    # The request passes every gate and reaches the first evaluation.
    monkeypatch.delenv("INVISIBLEBENCH_CASES")

    def evaluation(*args, **kwargs):
        raise EvalCalled

    monkeypatch.setattr(run, "inspect_eval", evaluation)
    with pytest.raises(EvalCalled):
        run.main(["--out", str(tmp_path / "run"), "--family", NAME, "--cases",
                  str(outside.parent), "--target", "mockllm/model", "--judge", "mockllm/model"])

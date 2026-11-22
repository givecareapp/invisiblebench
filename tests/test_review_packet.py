"""Tests for blind review packet generation, including external --cases folders."""

import json
import os
import shutil
import subprocess
import sys

import pytest
from inspect_ai import eval as inspect_eval
from inspect_ai.model import ModelOutput, get_model

from review_packet import build_packet
from task import CASES_ENV, ROOT, conversation_family


def _copy_external_family(tmp_path, name="ext_review_family"):
    external = tmp_path / "external_cases"
    dest = external / name
    shutil.copytree(ROOT / "cases" / "backup_care", dest)
    case = json.loads((dest / "case.json").read_text(encoding="utf-8"))
    case["id"] = name
    (dest / "case.json").write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
    rubric = json.loads((dest / "rubric.json").read_text(encoding="utf-8"))
    rubric["family"] = name
    (dest / "rubric.json").write_text(json.dumps(rubric, indent=2) + "\n", encoding="utf-8")
    return external, name


def test_build_packet_supports_external_cases_and_restores_env(tmp_path, monkeypatch):
    external, family = _copy_external_family(tmp_path)
    monkeypatch.setenv(CASES_ENV, str(external))
    model = get_model(
        "mockllm/model",
        custom_outputs=[ModelOutput.from_content("mockllm/model", "Reply text.") for _ in range(12)],
    )
    log = inspect_eval(
        conversation_family(family),
        model=model,
        log_dir=str(tmp_path / "gen"),
        display="none",
    )[0]

    # Clear the env var and verify --cases / cases= locates the external family cleanly.
    monkeypatch.delenv(CASES_ENV, raising=False)
    packet = build_packet(log.location, cases=external)
    assert packet["family"] == family
    assert packet["complete_conversations"] == 3
    assert packet["items"]
    assert CASES_ENV not in os.environ

    # Verify CLI --cases produces the same JSON packet.
    proc = subprocess.run(
        [sys.executable, str(ROOT / "review_packet.py"), "--cases", str(external), log.location],
        capture_output=True,
        text=True,
        check=True,
    )
    cli_packet = json.loads(proc.stdout)
    assert cli_packet == packet

    rubric = external / family / "rubric.json"
    rubric.write_bytes(rubric.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="rubric"):
        build_packet(log.location, cases=external)

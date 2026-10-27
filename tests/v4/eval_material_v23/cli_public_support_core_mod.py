"""Independent CLI expectations; every generated report stays under mod/private."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tools.eval_material_v23 import __main__ as cli

ROOT = Path(__file__).resolve().parents[3]
COUNTS = {"unverified": 51, "blocked_decision": 1, "blocked_dependency": 7, "observed_pass": 0}
SUBPROCESS_CODE = """
import os
import runpy
import socket
import sys
from datetime import UTC, datetime
from mingjing_core.timekit import clock

for key in ('KIMI_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','LANGSMITH_API_KEY','LANGCHAIN_API_KEY'):
    os.environ.pop(key,None)
os.environ['LANGCHAIN_TRACING_V2']='false'
os.environ['LANGSMITH_TRACING']='false'
def blocked(*args,**kwargs):
    raise AssertionError('offline_cli_network_forbidden')
for name in ('connect','connect_ex','sendto'):
    setattr(socket.socket,name,blocked)
for name in ('create_connection','getaddrinfo'):
    setattr(socket,name,blocked)
clock.SystemClock=lambda:clock.FrozenClock(datetime(2026,10,20,23,30,tzinfo=UTC))
sys.argv=['tools.eval_material_v23','--output',sys.argv[1]]
runpy.run_module('tools.eval_material_v23',run_name='__main__')
"""


def private_path(tmp_path: Path, name: str) -> Path:
    assert tmp_path.resolve().is_relative_to(ROOT / "private")
    return tmp_path / name


def no_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        raise AssertionError("rejected_cli_path_must_not_load_or_generate")

    monkeypatch.setattr(cli, "load_materials", forbidden)


def assert_readiness(path: Path, stdout: str) -> dict[str, Any]:
    raw = path.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")
    report = json.loads(raw)
    assert report["schema"] == "eval-material-readiness-v1"
    assert report["contract"] == "deterministic-eval-v2.3.0-candidate-material-v1"
    assert report["generated_at"] == "2026-10-21T07:30:00+08:00"
    assert report["case_count"] == 59 and report["assertion_count"] == 189
    assert report["counts"] == COUNTS
    assert len(report["cases"]) == 59 and len({case["id"] for case in report["cases"]}) == 59
    assert all(case["status"] != "observed_pass" for case in report["cases"])
    assert report["scope"] == "material and checker readiness; no product scenario executed"
    assert json.loads(stdout) == {"case_count": 59, "counts": COUNTS}
    return report


def child_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        environment.pop(name, None)
    environment.update(
        PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false"
    )
    return environment

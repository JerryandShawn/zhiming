"""Synthetic providers only; PG rows and HTTP framing remain the actual product path."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.timekit.clock import get_clock, set_clock
from tests.v4.agent.test_loop_cycle_support import ScriptedPort, answer
from tests.v4.agent.test_runtime_assembly_pg import configure, service
from tests.v4.streaming_integration.event_http_support import isolate


@pytest.fixture(name="legacy_repo")
def repository(p2_repo: Any, monkeypatch: Any) -> Iterator[Any]:
    isolate(monkeypatch)
    original = get_clock()
    try:
        yield p2_repo
    finally:
        set_clock(original)


def flat_frames(text: str) -> list[dict[str, Any]]:
    return [
        json.loads(line[5:].strip())
        for line in text.splitlines()
        if line.startswith("data:") and line[5:].strip() != "[DONE]"
    ]


def completed(repo: Any, *, port: Any = None) -> tuple[Any, dict, list[dict]]:
    configure(repo)
    core = service(repo, port or ScriptedPort([answer("合成兼容终稿")]))
    run = core.submit(
        owner="alice", request_id=uuid.uuid4().hex, message="请记住我喜欢合成蓝杯"
    )
    final = core.execute("alice", run["id"])
    current = repo.fetch_run("alice", run["id"])
    assert current["status"] == "succeeded" and current["result"] == final
    events = RunEventReader(repo, "alice", run["id"]).page(0)[0]
    return core, current, events

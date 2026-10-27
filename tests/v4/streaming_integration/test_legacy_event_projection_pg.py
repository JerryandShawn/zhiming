"""Legacy final/error authorization is current PG state, never an old buffered event."""

from __future__ import annotations

import asyncio
import copy
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.adapters.legacy_run_events import legacy_event_response
from mingjing_core.adapters.thread_events import event_response
from mingjing_core.application.event_retention import EventRetentionSweep
from mingjing_core.application.legacy_stream_projection import LegacyStreamProjection
from mingjing_core.application.read_result import read_result
from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.event_retention_metadata import terminal_anchor
from mingjing_core.timekit.clock import FrozenClock, set_clock
from tests.v4.agent.test_legacy_dom_runtime_pg import SavingPort
from tests.v4.agent.test_loop_cycle_support import ScriptedPort, answer
from tests.v4.agent.test_runtime_assembly_pg import configure, service
from tests.v4.streaming_integration.legacy_event_support import completed
from tests.v4.streaming_integration.legacy_event_support import repository as repository


def test_final_is_outer_read_projection_not_a_changed_envelope(
    legacy_repo: Any,
) -> None:
    repo = legacy_repo
    _, run, events = completed(repo)
    before = copy.deepcopy(run["result"])
    projection = LegacyStreamProjection(repo, "alice", run["id"])
    frames = [frame for event in events for frame in projection.project(event)]
    result = next(frame for frame in frames if frame["type"] == "result")
    assert result["result"] == read_result(before)
    assert (
        result["result"]["answer"] == before["text"]
        and "memory_receipts" not in result["result"]
    )
    assert repo.fetch_run("alice", run["id"])["result"] == before
    assert all("v" not in frame for frame in frames)
    assert frames[0]["message_id"] == run["request"]["source_message_id"]


@pytest.mark.parametrize("damage", ["text", "message_id", "run_id"])
def test_tampered_final_cannot_become_legacy_result(
    legacy_repo: Any, damage: str
) -> None:
    repo = legacy_repo
    _, run, events = completed(repo)
    event = copy.deepcopy(next(event for event in events if event["type"] == "final"))
    if damage == "text":
        event["data"]["envelope"]["text"] = "伪造兼容终稿"
    elif damage == "message_id":
        event["data"]["message_id"] = event["data"]["envelope"]["message_id"] = (
            "msg_synthetic_wrong"
        )
    else:
        event["data"]["run_id"] = "run_synthetic_wrong"
    with pytest.raises(EvidenceError):
        LegacyStreamProjection(repo, "alice", run["id"]).project(event)
    with pytest.raises(ScopeError):
        LegacyStreamProjection(repo, "bob", run["id"])


def test_generic_tool_receipt_is_only_safe_status_not_a_legacy_memory_card(
    legacy_repo: Any,
) -> None:
    repo = legacy_repo
    core, run, events = completed(repo, port=SavingPort(repo))
    tools = [event for event in events if event["type"] in {"tool_call", "tool_result"}]
    assert tools and len(run["result"]["receipts"]) == 1
    # Current Loop omits this optional event field. Exercise its allowed shape with
    # the actual completed write receipt; this is not evidence the producer emitted it.
    optional_receipt = copy.deepcopy(
        next(event for event in tools if event["type"] == "tool_result")
    )
    optional_receipt["data"]["receipt"] = run["result"]["receipts"][0]
    projection = LegacyStreamProjection(repo, "alice", run["id"])
    for event in [*tools, optional_receipt]:
        frames = projection.project(event)
        assert (
            len(frames) == 1
            and frames[0]["type"] == "status"
            and frames[0]["stage"] == "tool"
        )
        assert frames[0]["text"] == event["data"]["summary"]
        assert not {"receipt", "name", "arguments", "reasoning"}.intersection(frames[0])
    assert len(core.runtime_assembly.agent.port.requests) == 2
    assert len(run["result"]["receipts"]) == 1


def test_old_failed_attempt_error_is_not_replayed_as_error_after_current_success(
    legacy_repo: Any,
) -> None:
    repo = legacy_repo
    configure(repo)
    core = service(repo, ScriptedPort([answer("合成重试终稿")]))
    run = core.submit(
        owner="alice", request_id="old-error-success", message="合成重试问题"
    )
    failed = repo.claim_run("alice", run["id"])
    repo.fail_run(
        "alice", run["id"], "synthetic fixture failure", failed["lease_token"]
    )
    old = RunEventReader(repo, "alice", run["id"]).page(0)[0][-1]
    assert old["type"] == "error"
    repo.prepare_retry("alice", run["id"])
    core.execute("alice", run["id"])
    projection = LegacyStreamProjection(repo, "alice", run["id"])
    assert projection.project(old) == []
    current = RunEventReader(repo, "alice", run["id"]).page(0)[0]
    frames = [frame for event in current for frame in projection.project(event)]
    assert [frame["type"] for frame in frames].count("result") == 1
    assert "error" not in [frame["type"] for frame in frames]


def test_same_failure_code_from_an_older_attempt_is_not_current_error(
    legacy_repo: Any,
) -> None:
    repo = legacy_repo
    configure(repo)
    core = service(repo, ScriptedPort([]))
    run = core.submit(
        owner="alice", request_id="old-error-new-error", message="合成失败问题"
    )
    errors = []
    for attempt in range(2):
        if attempt:
            repo.prepare_retry("alice", run["id"])
        active = repo.claim_run("alice", run["id"])
        repo.fail_run(
            "alice", run["id"], "synthetic fixture failure", active["lease_token"]
        )
        errors.append(RunEventReader(repo, "alice", run["id"]).page(0)[0][-1])
    assert errors[0]["data"]["code"] == errors[1]["data"]["code"]
    projection = LegacyStreamProjection(repo, "alice", run["id"])
    assert projection.project(errors[0]) == []
    assert projection.project(errors[1])[0]["type"] == "error"


def test_source_withdrawal_refuses_previously_buffered_final_and_progress(
    legacy_repo: Any,
) -> None:
    repo = legacy_repo
    core, run, events = completed(repo)
    projection = LegacyStreamProjection(repo, "alice", run["id"])
    original = core.memory.get_source("alice", run["request"]["source_message_id"])
    with repo.transaction("alice"):
        repo.delete(
            "alice", "message", original["id"], expected_revision=original["revision"]
        )
        repo.invalidate_derived("alice", [], [original["id"]])
    assert repo.fetch_run("alice", run["id"])["status"] == "revoked"
    assert all(projection.project(event) == [] for event in events)
    current = RunEventReader(repo, "alice", run["id"]).page(0)[0]
    projected = [frame for event in current for frame in projection.project(event)]
    assert [frame["type"] for frame in projected] == ["error"]
    assert projected[0]["code"] == "SOURCE_REVOKED"


def test_real_expiry_does_not_rebuild_a_legacy_result_from_run_result(
    legacy_repo: Any,
) -> None:
    repo = legacy_repo
    _, run, events = completed(repo)
    final = next(event for event in events if event["type"] == "final")
    projection = LegacyStreamProjection(repo, "alice", run["id"])
    anchor = terminal_anchor(run)
    assert anchor is not None
    from datetime import datetime

    set_clock(
        FrozenClock(
            datetime.fromisoformat(anchor["at"]) + timedelta(days=30, seconds=1)
        )
    )
    assert EventRetentionSweep(repo).tick()["closed"] == 1

    async def connected() -> bool:
        return False

    request = SimpleNamespace(headers={}, scope={}, is_disconnected=connected)

    async def collect(response: Any) -> str:
        return "".join([part async for part in response.body_iterator])

    assert (
        asyncio.run(collect(legacy_event_response(repo, "alice", run["id"], request)))
        == "data: [DONE]\n\n"
    )
    assert asyncio.run(collect(event_response(repo, "alice", run["id"], request))) == ""
    assert projection.project(final) == []
    assert repo.fetch_run("alice", run["id"])["result"] == run["result"]

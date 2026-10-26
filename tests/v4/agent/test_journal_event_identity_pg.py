"""Native PG steps/events keep their identity through real tool crash windows."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.journal import JournalStep
from mingjing_core.application.agent_event_receipts import KEY
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

from .test_agent_runtime_pg import queued
from .test_agent_runtime_recovery_pg import fact
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, modify, writer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="event_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def _execute(repo: PostgresRepository, run: dict, port: ScriptedPort, callback: Callable[[dict], None]) -> dict:
    runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True)
    return runtime.execute(SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"], callback)


def _events(repo: PostgresRepository, run: dict) -> list[dict]:
    with repo.transaction("alice") as connection:
        return connection.execute(
            sql.SQL("SELECT seq,kind,payload FROM {} WHERE owner='alice' AND run_id=%s ORDER BY seq").format(
                repo.table("core_run_events")
            ),
            (run["id"],),
        ).fetchall()


def _steps(repo: PostgresRepository, run: dict) -> list[dict]:
    with repo.transaction("alice") as connection:
        return connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner='alice' AND run_id=%s ORDER BY epoch,seq").format(
                repo.table("core_run_steps")
            ),
            (run["id"],),
        ).fetchall()


def _reclaim(repo: PostgresRepository, run: dict) -> dict:
    modify(repo, run, "lease_until=now()-interval '1 second'")
    assert repo.recover_runs("alice") == 1
    return repo.claim_run("alice", run["id"], lease_seconds=150)


def _view(repo: PostgresRepository, run: dict) -> str:
    return fingerprint({"events": _events(repo, run), "usage": repo.fetch_run("alice", run["id"])["usage"]})


def _started_payload(run: dict) -> dict:
    return {"thread_id": "life:self", "message_id": run["request"]["source_message_id"], "incognito": False}


def test_same_epoch_crash_gaps_complete_one_real_effect_and_keep_original_events(
    event_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, record_property: Callable[[str, object], None]
) -> None:
    repo, port = event_repo, ScriptedPort([])
    run = queued(repo)
    port.responses = [answer("", [ToolCall("remember", "memory_write", writer(run))]), answer("已记录〔f1〕")]
    original, crashes, observed = RuntimeEvents.tool_event, [], []

    def crash(self: RuntimeEvents, step: JournalStep, kind: str, payload: dict) -> None:
        if kind == "tool_call" and not crashes:
            crashes.append("journal_before_call")
            raise SystemExit("synthetic journal-before-event crash")
        if kind == "tool_result" and len(crashes) == 1:
            crashes.append("completed_before_result")
            raise SystemExit("synthetic completed-before-event crash")
        original(self, step, kind, payload)

    monkeypatch.setattr(RuntimeEvents, "tool_event", crash)
    with pytest.raises(SystemExit):
        _execute(repo, run, port, observed.append)
    first = _events(repo, run)
    assert len([row for row in first if row["kind"] == "started"]) == 1
    assert not any(row["kind"].startswith("tool_") for row in first)
    assert _steps(repo, run)[-1]["status"] == "started" and repo.list("alice", "fact") == []
    run = _reclaim(repo, run)
    with pytest.raises(SystemExit):
        _execute(repo, run, port, observed.append)
    preserved = [row for row in _events(repo, run) if row["kind"] in {"started", "tool_call"}]
    assert len(preserved) == 2 and len(repo.list("alice", "fact")) == 1
    assert _steps(repo, run)[-1]["status"] == "completed"
    assert not any(row["kind"] == "tool_result" for row in _events(repo, run))
    run = _reclaim(repo, run)
    result = _execute(repo, run, port, observed.append)
    rows = _events(repo, run)
    assert [row for row in rows if row["kind"] in {"started", "tool_call"}] == preserved
    assert len([row for row in rows if row["kind"] == "tool_result"]) == 1
    assert result["text"] == "已记录〔f1〕" and len(repo.list("alice", "fact")) == 1 and len(port.requests) == 2
    with repo.transaction("alice") as connection:
        count = connection.execute(
            sql.SQL("SELECT count(*) AS n FROM {} WHERE owner='alice' AND operation='agent_memory_write'").format(
                repo.table("core_mutation_requests")
            )
        ).fetchone()["n"]
    assert count == 1
    state = repo.fetch_run("alice", run["id"])["usage"][KEY]
    assert len(state["receipts"]) == 3 and run["request"]["message"] not in json.dumps(state, ensure_ascii=False)
    record_property("actual_crash_gaps", ",".join(crashes))
    record_property("actual_scripted_model_streams", len(port.requests))
    record_property("real_memory_effects", count)


def _ordinary_retry(repo: PostgresRepository) -> None:
    run, observed, crashes = queued(repo), [], []
    port = ScriptedPort(
        [
            answer("", [ToolCall("same-legal-id", "time_context", {})]),
            answer("", [ToolCall("same-legal-id", "time_context", {})]),
            answer("合成显式重试完成"),
        ]
    )

    def observe(event: dict) -> None:
        observed.append(event)
        if event["type"] == "tool_result" and not crashes:
            crashes.append(True)
            raise SystemExit("synthetic committed-result crash")

    with pytest.raises(SystemExit):
        _execute(repo, run, port, observe)
    original = [row for row in _events(repo, run) if row["kind"] in {"started", "tool_call", "tool_result"}]
    source = repo.get("alice", "message", run["request"]["source_message_id"])
    repo.update("alice", "message", source["id"], {"synthetic_marker": True}, expected_revision=source["revision"])
    repo.fail_run("alice", run["id"], "synthetic explicit retry", run["lease_token"])
    retried = repo.prepare_retry("alice", run["id"])["run"]
    assert retried["retry_epoch"] == 1
    current = repo.claim_run("alice", run["id"], lease_seconds=150)
    assert _execute(repo, current, port, observe)["text"] == "合成显式重试完成"
    rows = _events(repo, run)
    assert [row for row in rows if row["seq"] in {item["seq"] for item in original}] == original
    assert len([row for row in rows if row["kind"] == "started"]) == 1
    tools = [row for row in rows if row["kind"].startswith("tool_")]
    assert len(tools) == 4 and {row["payload"]["call_id"] for row in tools} == {"same-legal-id"}
    assert all(row["payload"] for row in tools) and len(port.requests) == 3


def test_native_retry_regeneration_reuse_raw_id_and_concurrent_result_has_one_identity(
    event_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, record_property: Callable[[str, object], None]
) -> None:
    repo, memory = event_repo, MemoryService(event_repo)
    original, observed, withdrawn, raced = RuntimeEvents.tool_event, [], [], []

    def race(self: RuntimeEvents, step: JournalStep, kind: str, payload: dict) -> None:
        if step.epoch == 1 and kind == "tool_result":
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(original, self, step, kind, payload) for _ in range(2)]
                for future in futures:
                    future.result()
            raced.append(step.seq)
        else:
            original(self, step, kind, payload)

    def observe(event: dict) -> None:
        observed.append(copy.deepcopy(event))
        if event["type"] == "tool_result" and not withdrawn:
            withdrawn.append(True)
            memory.retire_fact("alice", old["id"], expected_revision=old["revision"], scope="source")

    monkeypatch.setattr(RuntimeEvents, "tool_event", race)
    _ordinary_retry(repo)
    old, run = fact(repo), queued(repo, "现在请给合成建议")
    port = ScriptedPort(
        [
            answer("", [ToolCall("same-legal-id", "time_context", {})]),
            answer("", [ToolCall("same-legal-id", "time_context", {})]),
            answer("干净的新答复"),
        ]
    )
    result = _execute(repo, run, port, observe)
    current, rows = repo.fetch_run("alice", run["id"]), _events(repo, run)
    assert current["retry_epoch"] == 1 and current["usage"]["agent_runtime"]["regenerations"] == 1
    assert result["text"] == "干净的新答复" and raced and len(port.requests) == 3
    assert len([row for row in rows if row["kind"] == "started"]) == 1
    assert [row["kind"] for row in rows if row["kind"].startswith("tool_")] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
    ]
    calls = [event["data"] for event in observed if event["type"] == "tool_call"]
    assert len(calls) == 2 and {event["call_id"] for event in calls} == {"same-legal-id"}
    assert calls[0]["seq"] != calls[1]["seq"]
    assert all(not row["payload"] for row in rows if row["seq"] <= calls[0]["seq"] + 1)
    state = current["usage"][KEY]
    assert set(state["epochs"]) == {"0", "1"} and len(state["receipts"]) == 5
    assert {row["epoch"] for row in _steps(repo, run) if row["kind"] == "tool"} == {0, 1}
    assert any(event["type"] == "text_reset" for event in observed)
    record_property("actual_epochs", "0,1 via prepare_retry/claim and AgentRegenerator")
    record_property("concurrent_result_writers", 2)
    record_property("native_tool_event_rows", 4)


def _tamper_rejected(repo: PostgresRepository, run: dict, step: JournalStep, mode: str, payload: dict) -> None:
    with pytest.raises(SystemExit, match="synthetic rollback"), repo.transaction("alice") as connection:
        if mode == "event":
            event = next(row for row in _events(repo, run) if row["kind"] == "tool_call")
            changed = dict(event["payload"], ts="2026-10-18T20:00:01+08:00")
            connection.execute(
                sql.SQL("UPDATE {} SET payload=%s WHERE owner='alice' AND run_id=%s AND seq=%s").format(
                    repo.table("core_run_events")
                ),
                (Jsonb(changed), run["id"], event["seq"]),
            )
        else:
            usage = copy.deepcopy(repo.fetch_run("alice", run["id"])["usage"])
            if mode == "missing_started":
                usage[KEY]["receipts"].pop("started")
                connection.execute(
                    sql.SQL("DELETE FROM {} WHERE owner='alice' AND run_id=%s AND kind='started'").format(
                        repo.table("core_run_events")
                    ),
                    (run["id"],),
                )
            else:
                usage[KEY]["receipts"][f"e{step.epoch}:s{step.seq}:tool_call"]["identity_sha256"] = "0" * 64
            connection.execute(
                sql.SQL("UPDATE {} SET usage=%s WHERE owner='alice' AND id=%s").format(repo.table("core_runs")),
                (Jsonb(usage), run["id"]),
            )
        before = _view(repo, run)
        with pytest.raises(EvidenceError):
            events = RuntimeEvents(repo, run, None)
            if mode == "missing_started":
                events.send("started", _started_payload(run))
            else:
                events.tool_event(step, "tool_call", payload)
        assert _view(repo, run) == before
        raise SystemExit("synthetic rollback")


def test_tampered_events_receipts_foreign_step_and_native_withdrawal_never_append_or_resurrect(
    event_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, record_property: Callable[[str, object], None]
) -> None:
    repo, run = event_repo, queued(event_repo)
    original, saved = RuntimeEvents.tool_event, []

    def crash(self: RuntimeEvents, step: JournalStep, kind: str, payload: dict) -> None:
        original(self, step, kind, payload)
        saved.append((step, dict(payload)))
        raise SystemExit("synthetic committed-call crash")

    monkeypatch.setattr(RuntimeEvents, "tool_event", crash)
    with pytest.raises(SystemExit):
        _execute(repo, run, ScriptedPort([answer("", [ToolCall("clock", "time_context", {})])]), lambda event: None)
    monkeypatch.setattr(RuntimeEvents, "tool_event", original)
    step, payload = saved[0]
    for mode in ("event", "receipt", "missing_started"):
        _tamper_rejected(repo, run, step, mode, payload)
    before = _view(repo, run)
    with pytest.raises(EvidenceError):
        RuntimeEvents(repo, run, None).tool_event(replace(step, owner="bob"), "tool_call", payload)
    assert _view(repo, run) == before
    memory = MemoryService(repo)
    source = memory.save_fact(
        "alice", "self", run["request"]["source_message_id"], run["request"]["message"], "preference"
    )
    memory.retire_fact("alice", source["id"], expected_revision=source["revision"], scope="source")
    before = _view(repo, run)
    with pytest.raises(CoreError):
        RuntimeEvents(repo, run, None).tool_event(step, "tool_call", payload)
    with pytest.raises(CoreError):
        RuntimeEvents(repo, run, None).send("started", _started_payload(run))
    assert _view(repo, run) == before and all(row["payload"] == {} for row in _events(repo, run))
    assert all(row["output"] is None and row["error_code"] == "SOURCE_REVOKED" for row in _steps(repo, run))
    assert KEY in repo.fetch_run("alice", run["id"])["usage"]
    record_property("tampering", "actual event timestamp and receipt identity")
    record_property("privacy", "actual current source withdrawn; no public payload restored")

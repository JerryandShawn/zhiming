"""Frozen first requests survive real PG writes/reclaims, never revoked sources."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from threading import Barrier
from typing import Any

import httpx
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_budget import assert_live_allowed
from mingjing_core.agent.context_types import ContextBuild, InputMeterUnverified
from mingjing_core.application.agent_snapshots import STAGE, AgentSnapshotStore
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, RevisionConflict, ScopeError
from mingjing_core.models.port import ChatMessage, ToolCall, ToolSpec
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock


@pytest.fixture
def snapshots(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("快照PG测试禁止外部传输")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    monkeypatch.setattr("subprocess.run", reject)
    for key in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "LANGSMITH_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    old = get_clock()
    set_clock(FrozenClock(datetime(2026, 10, 18, 12, tzinfo=UTC)))
    try:
        yield p2_repo
    finally:
        set_clock(old)


def run_for(repo: PostgresRepository, text: str = "我喜欢合成夜班", **request: Any) -> dict[str, Any]:
    source = MemoryService(repo).receive("alice", content=text, source_id=os.urandom(8).hex(), at=get_clock().now())
    run = repo.queue_run("alice", os.urandom(8).hex(), {"message": text, "source_message_id": source["id"], **request})
    modify(repo, run, "runtime='v4',thread_id='life:self'")
    return repo.claim_run("alice", run["id"], lease_seconds=3600)


def modify(repo: PostgresRepository, run: dict[str, Any], clause: str) -> None:
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET {} WHERE owner=%s AND id=%s").format(repo.table("core_runs"), sql.SQL(clause)),
            ("alice", run["id"]),
        )


def build(repo: PostgresRepository, run: dict[str, Any], **kwargs: Any) -> ContextBuild:
    return ContextEngine(MemoryService(repo), "合成测试系统", clock=get_clock()).build(
        "alice", run["request"]["source_message_id"], **kwargs
    )


def saved(repo: PostgresRepository, run: dict[str, Any]) -> dict[str, Any]:
    return repo.get("alice", "runtime_step", f"{run['id']}:e{run['retry_epoch']}:{STAGE}", include_deleted=True)


def never() -> ContextBuild:
    raise AssertionError("重放不得重新装配上下文")


def test_full_dataclasses_and_private_reasoning_replay_after_repository_reopen(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)
    cycle = (
        ChatMessage(
            "assistant",
            "合成工具请求",
            [ToolCall("call", "lookup", {"text": "合成参数"})],
            reasoning="合成受控推理",
            reasoning_signature="合成签名",
            tool_cycle="run:e0",
        ),
        ChatMessage("tool", '{"ok":true}', tool_call_id="call", tool_cycle="run:e0"),
    )
    tools = (ToolSpec("lookup", "合成工具", {"type": "object", "properties": {"text": {"type": "string"}}}),)
    original = build(repo, run, current_epoch_messages=cycle, tools=tools)
    first = AgentSnapshotStore(repo).load_or_build(run, lambda: original)
    assert asdict(first) == asdict(original)
    frozen = copy.deepcopy(first)
    first.alias_map["injected"] = {"id": "not-persisted"}
    first.budget.tools[0].parameters["properties"]["new"] = {"type": "integer"}
    first.messages[-2].tool_calls[0].arguments["text"] = "已改变的返回对象"
    reopened = PostgresRepository(repo.dsn, schema=repo.schema, initialize=False)
    try:
        replay = AgentSnapshotStore(reopened).load_or_build(run, never)
        assert asdict(replay) == asdict(frozen)
    finally:
        reopened.close()
    state = repo.fetch_run("alice", run["id"])
    assert state["state_version"] == original.injected_versions and state["calls"] == 0
    assert state["checkpoint"]["ids"] == [saved(repo, run)["id"]]
    assert "合成受控推理" not in json.dumps(state["checkpoint"], ensure_ascii=False)
    assert saved(repo, run)["source_ids"] == [run["request"]["source_message_id"]]
    with pytest.raises(InputMeterUnverified):
        assert_live_allowed(replay.budget)


def test_new_fact_writer_changes_l2_but_never_rebuilds_first_request(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)
    store = AgentSnapshotStore(repo)
    first = store.load_or_build(run, lambda: build(repo, run))
    revision = repo.get_revision("alice")
    source_id = run["request"]["source_message_id"]
    fact = MemoryService(repo).save_fact("alice", "self", source_id, run["request"]["message"], "preference")
    assert fact["write_status"] == "saved" and repo.get_revision("alice") > revision
    assert build(repo, run).messages != first.messages
    replay = store.load_or_build(run, never)
    assert asdict(replay) == asdict(first)
    assert "fact:" + fact["id"] not in repo.fetch_run("alice", run["id"])["state_version"]


def test_reclaim_new_lease_replays_same_epoch_old_lease_rejected(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)
    first = AgentSnapshotStore(repo).load_or_build(run, lambda: build(repo, run))
    modify(repo, run, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", run["id"], lease_seconds=3600)
    assert reclaimed["lease_token"] != run["lease_token"]
    assert asdict(AgentSnapshotStore(repo).load_or_build(reclaimed, never)) == asdict(first)
    with pytest.raises(LeaseConflict):
        AgentSnapshotStore(repo).load_or_build(run, never)


@pytest.mark.parametrize("scope", ["fact", "source"])
def test_real_withdrawal_purges_private_snapshot_and_cannot_resurrect(
    snapshots: PostgresRepository, scope: str
) -> None:
    repo, memory = snapshots, MemoryService(snapshots)
    source = memory.receive("alice", content="我不能上合成夜班", source_id="constraint", at=get_clock().now())
    fact = memory.save_fact("alice", "self", source["id"], source["content"], "constraint")
    run = run_for(repo, "帮我分析合成安排")
    AgentSnapshotStore(repo).load_or_build(run, lambda: build(repo, run))
    assert saved(repo, run)["fact_ids"] == [fact["id"]]
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope=scope)
    assert saved(repo, run)["status"] == "deleted" and "output" not in saved(repo, run)
    assert repo.fetch_run("alice", run["id"])["checkpoint"] == {}
    with pytest.raises(LeaseConflict):
        AgentSnapshotStore(repo).load_or_build(run, never)
    # Even a hostile restoration of the lease must not treat an erased row as a cache miss.
    modify(repo, run, "status='running',lease_token='synthetic-new',lease_until=now()+interval '1 hour'")
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET request=%s WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
            (Jsonb(run["request"]), "alice", run["id"]),
        )
    restored = repo.fetch_run("alice", run["id"])
    with pytest.raises(EvidenceError):
        AgentSnapshotStore(repo).load_or_build(restored, never)


@pytest.mark.parametrize(
    "clause",
    [
        "cancel_requested_at=now()",
        "deadline_at='2020-01-01Z'",
        "status='cancelled'",
        "lease_until=now()-interval '1 second'",
        "retry_epoch=retry_epoch+1",
        "runtime='v3'",
    ],
)
def test_invalid_authority_never_calls_builder(snapshots: PostgresRepository, clause: str) -> None:
    run = run_for(snapshots)
    modify(snapshots, run, clause)
    with pytest.raises((LeaseConflict, ScopeError)):
        AgentSnapshotStore(snapshots).load_or_build(run, never)
    assert snapshots.list("alice", "runtime_step") == []


@pytest.mark.parametrize("changes", [{"owner": "bob"}, {"subject": "other"}, {"retry_epoch": True}])
def test_forged_identity_never_reads_cached_private_context(
    snapshots: PostgresRepository, changes: dict[str, Any]
) -> None:
    run = run_for(snapshots)
    AgentSnapshotStore(snapshots).load_or_build(run, lambda: build(snapshots, run))
    with pytest.raises((ScopeError, LeaseConflict)):
        AgentSnapshotStore(snapshots).load_or_build(dict(run, **changes), never)


def test_partial_revocation_ledger_without_cleanup_still_blocks_replay(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)
    store = AgentSnapshotStore(repo)
    store.load_or_build(run, lambda: build(repo, run))
    with repo.transaction("alice") as connection:
        repo.revoke(
            connection,
            "alice",
            "source_span",
            "hostile-partial",
            "stopped",
            {"message_id": run["request"]["source_message_id"], "start": 0, "end": 2},
        )
    with pytest.raises(RevisionConflict):
        store.load_or_build(run, never)


def test_revocation_during_builder_never_persists_stale_body(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)

    def racing() -> ContextBuild:
        result = build(repo, run)
        with repo.transaction("alice") as connection:
            repo.revoke(
                connection,
                "alice",
                "source_span",
                "during-build",
                "stopped",
                {"message_id": run["request"]["source_message_id"], "start": 0, "end": 2},
            )
        return result

    with pytest.raises(RevisionConflict):
        AgentSnapshotStore(repo).load_or_build(run, racing)
    assert repo.list("alice", "runtime_step") == []
    assert repo.fetch_run("alice", run["id"])["state_version"] == {}


def test_unknown_codec_field_rejects_without_rebuild(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)
    AgentSnapshotStore(repo).load_or_build(run, lambda: build(repo, run))
    row = saved(repo, run)
    output = copy.deepcopy(row["output"])
    output["budget"]["messages"][0]["future_unknown_reasoning"] = "合成未来字段"
    repo.update(
        "alice",
        "runtime_step",
        row["id"],
        {"output": output, "output_sha256": fingerprint(output)},
        expected_revision=row["revision"],
    )
    with pytest.raises(EvidenceError):
        AgentSnapshotStore(repo).load_or_build(run, never)


def test_two_repositories_compete_without_holding_owner_lock_during_builder(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)
    other = PostgresRepository(repo.dsn, schema=repo.schema, initialize=False)
    barrier = Barrier(2)

    def execute(current: PostgresRepository) -> ContextBuild:
        def construct() -> ContextBuild:
            result = build(current, run)
            barrier.wait(timeout=15)
            return result

        return AgentSnapshotStore(current).load_or_build(run, construct)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(execute, (repo, other)))
        assert asdict(results[0]) == asdict(results[1])
        assert len(repo.list("alice", "runtime_step")) == 1
    finally:
        other.close()


def test_incognito_and_builder_failure_leave_no_snapshot(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots, incognito=True)
    with pytest.raises(ScopeError):
        AgentSnapshotStore(repo).load_or_build(run, never)
    assert repo.list("alice", "runtime_step") == []
    ordinary = run_for(repo)
    with pytest.raises(AssertionError):
        AgentSnapshotStore(repo).load_or_build(ordinary, never)
    assert repo.list("alice", "runtime_step") == []


def test_dependency_change_during_build_never_replaces_registered_versions(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)

    def racing() -> ContextBuild:
        result = build(repo, run)
        source_id = run["request"]["source_message_id"]
        repo.update("alice", "message", source_id, {"synthetic_metadata": True}, expected_revision=1)
        return result

    with pytest.raises(RevisionConflict):
        AgentSnapshotStore(repo).load_or_build(run, racing)
    assert repo.list("alice", "runtime_step") == []
    assert repo.fetch_run("alice", run["id"])["state_version"] == {}


def test_new_epoch_has_its_own_initial_snapshot_without_reusing_old_messages(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)
    store = AgentSnapshotStore(repo)
    first = store.load_or_build(run, lambda: build(repo, run))
    modify(repo, run, "retry_epoch=retry_epoch+1")
    newer = repo.fetch_run("alice", run["id"])
    second = store.load_or_build(
        newer,
        lambda: ContextEngine(MemoryService(repo), "合成新批次系统").build(
            "alice", run["request"]["source_message_id"]
        ),
    )
    assert second.messages != first.messages
    assert len(repo.list("alice", "runtime_step")) == 2
    assert asdict(store.load_or_build(newer, never)) == asdict(second)
    with pytest.raises(LeaseConflict):
        store.load_or_build(run, never)


@pytest.mark.parametrize("column", ["request", "state_version", "changed_initial_version"])
def test_persisted_request_or_dependencies_cannot_be_silently_replaced(
    snapshots: PostgresRepository, column: str
) -> None:
    repo, run = snapshots, run_for(snapshots)
    store = AgentSnapshotStore(repo)
    first = store.load_or_build(run, lambda: build(repo, run))
    value = dict(run["request"], new_scope=True) if column == "request" else {}
    if column == "changed_initial_version":
        column, value = "state_version", {key: version + 1 for key, version in first.injected_versions.items()}
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET {}=%s WHERE owner=%s AND id=%s").format(
                repo.table("core_runs"), sql.Identifier(column)
            ),
            (Jsonb(value), "alice", run["id"]),
        )
    with pytest.raises(RevisionConflict):
        store.load_or_build(run, never)
    assert saved(repo, run)["output_sha256"] == fingerprint(asdict(first))


def test_deleting_current_source_purges_even_a_fact_written_after_snapshot(snapshots: PostgresRepository) -> None:
    repo, run = snapshots, run_for(snapshots)
    store = AgentSnapshotStore(repo)
    store.load_or_build(run, lambda: build(repo, run))
    memory = MemoryService(repo)
    fact = memory.save_fact(
        "alice", "self", run["request"]["source_message_id"], run["request"]["message"], "preference"
    )
    assert "fact:" + fact["id"] not in repo.fetch_run("alice", run["id"])["state_version"]
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    assert saved(repo, run)["status"] == "deleted" and "output" not in saved(repo, run)
    with pytest.raises(LeaseConflict):
        store.load_or_build(run, never)


def test_verified_new_tool_dependencies_do_not_change_frozen_request_after_reopen(
    snapshots: PostgresRepository,
) -> None:
    repo, run = snapshots, run_for(snapshots)
    first = AgentSnapshotStore(repo).load_or_build(run, lambda: build(repo, run))
    fact = MemoryService(repo).save_fact(
        "alice", "self", run["request"]["source_message_id"], run["request"]["message"], "preference"
    )
    versions = dict(first.injected_versions, **{"fact:" + fact["id"]: fact["revision"]})
    repo.set_run_dependencies("alice", run["id"], versions, run["lease_token"])
    reopened = PostgresRepository(repo.dsn, schema=repo.schema, initialize=False)
    try:
        assert asdict(AgentSnapshotStore(reopened).load_or_build(run, never)) == asdict(first)
    finally:
        reopened.close()
    assert repo.fetch_run("alice", run["id"])["state_version"] == versions

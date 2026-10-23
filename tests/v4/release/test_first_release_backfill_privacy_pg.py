"""Native core4 history and privacy replay precede independent backfill effects."""

from __future__ import annotations

import importlib
import os
import uuid
from collections.abc import Iterator
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_first_release_backfill_effects_pg import checkpoint_fixture, state, table_rows

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.memory.projections import tokenized_payload
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.runtime import LangGraphRuntime
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tests.v4.agent.test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from tools.deploy_core import apply_withdrawals, export_withdrawals
from tools.eval.targets.local_db import local_dsn, verify_local_postgres
from tools.eval.targets.v4_scripted import ForbiddenLegacyModel
from tools.first_release_backfill_effects import verify_backfill_effects
from tools.first_release_backfill_expected import WRITES, BackfillBindings


@pytest.fixture
def privacy_case(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    dsn = os.getenv("CORE_TEST_DSN", "")
    if not dsn:
        pytest.skip("requires disposable loopback PostgreSQL 15")

    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("backfill privacy component forbids HTTP and child processes")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    monkeypatch.setattr("subprocess.run", reject)
    dsn, schema = local_dsn(dsn), "bf_privacy_" + uuid.uuid4().hex
    verify_local_postgres(dsn)
    # Native SDK setup and later native purge must use the same isolated tables.
    repo = PostgresRepository(
        make_conninfo(dsn, options="-c search_path=" + schema + ",public"), schema=schema, max_size=2
    )
    previous = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat("2026-10-17T10:30:00+08:00")))
    try:
        repo.ensure_owner("alice", settings={"runtime": "v4", "auto_save_low_sensitivity": True})
        repo.ensure_owner("bob")
        MemoryService(repo).receive("bob", content="合成另一用户保留原话", source_id="retained-bob")
        repo.mutation_request("bob", "backfill-privacy", "receipt", {}, lambda: {"status": "saved"})
        checkpoint_fixture(dsn, schema)
        module = importlib.import_module("mingjing_core.memory.backfill")
        bindings = BackfillBindings(MemoryService, module, tokenized_payload, fingerprint)
        yield SimpleNamespace(repo=repo, bindings=bindings)
    finally:
        set_clock(previous)
        with repo.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        repo.close()


def actual_core4(case: SimpleNamespace) -> SimpleNamespace:
    repo, memory = case.repo, MemoryService(case.repo)
    source = memory.receive("alice", content="请记住我只接受白班", source_id="fact-source")
    fact = memory.save_fact("alice", "self", source["id"], "我只接受白班", "constraint")
    assert fact["write_status"] == "saved"
    port = ScriptedPort([answer("先核对现实约束，再安排合适岗位〔f1〕。")])
    runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True)
    service = ConsultationService(
        repo,
        model=ForbiddenLegacyModel(),
        runtime=LangGraphRuntime(repo, initialize=False),
        agent_runtime=runtime,
    )
    thread = ThreadService(repo).create("alice", request_id="native-core4-thread")
    run = ThreadIngress(service).submit(
        owner="alice", thread_id=thread["id"], message="请根据实际约束安排下一步。", request_id="native-core4"
    )
    run = repo.claim_run("alice", run["id"], lease_seconds=150)
    result = runtime.execute(service, "alice", run["id"], run["lease_token"])
    assert result["schema"] == "core4.0" and result["used_fact_ids"] == [fact["id"]]
    assert len(port.requests) == 1
    return SimpleNamespace(run=repo.fetch_run("alice", run["id"]), result=result, fact=fact, source=source)


def checkpoint_counts(repo: PostgresRepository, run_id: str) -> list[int]:
    with repo.transaction() as connection:
        return [
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {} WHERE thread_id=%s").format(repo.table(name)),
                (run_id + ":e0",),
            ).fetchone()["n"]
            for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
        ]


def pending_checkpoint(repo: PostgresRepository, run_id: str) -> None:
    saver = PostgresSaver(repo.pool)
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"private": {"synthetic": ["withdrawn checkpoint content"]}}
    checkpoint["channel_versions"] = {"private": "1"}
    config = saver.put(
        {"configurable": {"thread_id": run_id + ":e0", "checkpoint_ns": ""}}, checkpoint, {}, {"private": "1"}
    )
    saver.put_writes(config, [("private", "withdrawn pending content")], "synthetic-native-task")
    assert checkpoint_counts(repo, run_id) == [1, 1, 1]


def assert_privacy_retained(case: SimpleNamespace, original: SimpleNamespace) -> None:
    repo, ident = case.repo, original.run["id"]
    run = repo.fetch_run("alice", ident)
    assert run["status"] == "revoked" and run["request"] == run["checkpoint"] == {}
    assert run["result"] is run["lease_token"] is run["lease_until"] is None
    fact = repo.get("alice", "fact", original.fact["id"], include_deleted=True)
    source = repo.get("alice", "message", original.source["id"], include_deleted=True)
    assert fact["status"] == source["status"] == "deleted"
    assert not fact.get("content") and not source.get("content")
    assert repo.search("alice", "self", ["白班"], ["message", "fact"], 20) == []
    assert checkpoint_counts(repo, ident) == [0, 0, 0]
    with repo.transaction("alice") as connection:
        events = connection.execute(
            sql.SQL("SELECT payload FROM {} WHERE owner='alice' AND run_id=%s").format(repo.table("core_run_events")),
            (ident,),
        ).fetchall()
        steps = connection.execute(
            sql.SQL("SELECT output FROM {} WHERE owner='alice' AND run_id=%s").format(repo.table("core_run_steps")),
            (ident,),
        ).fetchall()
    assert events and all(row["payload"] == {} for row in events)
    assert steps and all(row["output"] is None for row in steps)
    old_reply = repo.get("alice", "message", original.result["message_id"], include_deleted=True)
    assert old_reply.get("content") != original.result["text"]
    assert old_reply["status"] == "deleted" or old_reply.get("redacted") is True
    assistants = [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]
    assert all(row.get("redacted") and row.get("content") != original.result["text"] for row in assistants)


def test_real_core4_historical_reply_rebuild_has_exact_native_lineage_and_increment(
    privacy_case: SimpleNamespace,
) -> None:
    repo = privacy_case.repo
    original = actual_core4(privacy_case)
    # A synthetic historical gap removes only the actual message, never its result or lineage.
    with repo.transaction("alice") as connection:
        removed = connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner='alice' AND kind='message' AND id=%s RETURNING id").format(
                repo.table("core_entities")
            ),
            (original.result["message_id"],),
        ).fetchall()
    assert removed == [{"id": original.result["message_id"]}]
    before = state(repo)
    result = verify_backfill_effects(repo, "alice", bindings=privacy_case.bindings)
    assert result["first"]["assistant_created"] == 1
    assert result["first"] == result["preview"] and all(result["second"][key] == 0 for key in WRITES)
    expected_id = "msg_" + fingerprint(["alice", "assistant", original.run["id"]])[:32]
    reply = repo.get("alice", "message", expected_id)
    assert reply["id"] == original.result["message_id"] and reply["content"] == original.result["text"]
    assert reply["used_fact_ids"] == [original.fact["id"]] and reply["used_claim_ids"] == []
    assert {original.source["id"], original.run["request"]["source_message_id"]} <= set(reply["source_ids"])
    assert reply["policy"] == {"origin": "system", "run_context": False} and reply["revision"] == 1
    assert repo.fetch_run("alice", original.run["id"]) == original.run
    assert len(table_rows(repo, "core_operations")) == len(before.rows["core_operations"]) + 1
    assert result["new_assistants_verified"] == 1 and result["source_admission_verified"] is False


def test_native_withdrawal_replay_then_backfill_never_restores_body_run_or_checkpoint(
    privacy_case: SimpleNamespace,
) -> None:
    repo, memory = privacy_case.repo, MemoryService(privacy_case.repo)
    original = actual_core4(privacy_case)
    pending_checkpoint(repo, original.run["id"])
    memory.retire_fact(
        "alice", original.fact["id"], expected_revision=original.fact["revision"], operation="delete", scope="source"
    )
    assert checkpoint_counts(repo, original.run["id"]) == [1, 1, 1]
    ledger = export_withdrawals(repo)
    first = apply_withdrawals(repo, ledger)
    assert first["external_sends"] == first["model_calls"] == 0
    assert_privacy_retained(privacy_case, original)
    replayed = state(repo)
    apply_withdrawals(repo, ledger)
    assert state(repo) == replayed
    result = verify_backfill_effects(repo, "alice", bindings=privacy_case.bindings)
    assert result["first"]["assistant_created"] == 0
    assert all(result["second"][key] == 0 for key in WRITES)
    assert state(repo) == replayed and export_withdrawals(repo) == ledger
    assert_privacy_retained(privacy_case, original)

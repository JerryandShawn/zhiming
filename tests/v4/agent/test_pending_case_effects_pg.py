"""A real committed case write never licenses a changed or incomplete proof."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

from .test_agent_runtime_pg import invoke
from .test_loop_cycle_support import ScriptedPort, answer, modify
from .test_loop_cycle_support import cycle_repo as source_fixture
from .tool_effect_recovery_support import CrashBeforeAcknowledgement, business_state, prepare_intent, step_row


@pytest.fixture
def pending_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def corrupt(repo: PostgresRepository, run: dict[str, Any], seq: int, proof: str) -> None:
    steps, mutations, operations = (
        repo.table(name) for name in ("core_run_steps", "core_mutation_requests", "core_operations")
    )
    op = f"run:{run['id']}:e{run['retry_epoch']}:s{seq}"
    with repo.transaction("alice") as connection:
        if proof.startswith("pending_"):
            changes = {
                "pending_output": "output='{}'::jsonb",
                "pending_finished": "finished_at=now()",
                "pending_usage": "usage='{\"unexpected\":1}'::jsonb",
                "pending_error": "error_code='SOURCE_REVOKED'",
                "pending_input": "input_fp=repeat('a',64)",
                "pending_readonly": "name='memory_search'",
            }
            connection.execute(
                sql.SQL("UPDATE {} SET {} WHERE owner='alice' AND run_id=%s AND epoch=%s AND seq=%s").format(
                    steps, sql.SQL(changes[proof])
                ),
                (run["id"], run["retry_epoch"], seq),
            )
        elif proof in {"missing_model", "old_epoch_model"}:
            clause = "DELETE FROM {}" if proof == "missing_model" else "UPDATE {} SET epoch=epoch+1"
            connection.execute(
                sql.SQL(clause + " WHERE owner='alice' AND run_id=%s AND kind='model'").format(steps), (run["id"],)
            )
        elif proof.startswith("ledger_"):
            ledger_corruption(repo, run, proof)
        elif proof.startswith("entity_"):
            entity_corruption(repo, run, proof)
        elif proof.startswith("operation_"):
            clause = {
                "operation_missing": "DELETE FROM {}",
                "operation_wrong_id": "UPDATE {} SET result_id='foreign-case'",
                "operation_digest": "UPDATE {} SET fingerprint='invalid'",
                "operation_time": "UPDATE {} SET created_at=created_at-interval '1 minute'",
            }[proof]
            connection.execute(
                sql.SQL(clause + " WHERE owner='alice' AND operation_id=%s").format(operations), (op + ":case",)
            )
        else:
            clause = (
                "fingerprint=repeat('b',64)"
                if proof == "mutation_input"
                else "receipt=jsonb_set(receipt,'{revision}','99')"
            )
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET {} WHERE owner='alice' AND operation='agent_case_update' AND request_key=%s"
                ).format(mutations, sql.SQL(clause)),
                (op,),
            )


def entity_corruption(repo: PostgresRepository, run: dict[str, Any], proof: str) -> None:
    if proof == "entity_subject":
        repo.create_subject("alice", "foreign-subject", "合成范围外人物")
    clause = {
        "entity_field": "data=jsonb_set(data,'{state,goal}','\"伪造目标\"')",
        "entity_refs": "data=jsonb_set(data,'{source_refs}','[]')",
        "entity_subject": "subject='foreign-subject'",
    }[proof]
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET {} WHERE owner='alice' AND kind='case' AND id=%s").format(
                repo.table("core_entities"), sql.SQL(clause)
            ),
            (run["request"]["case_ids"][0],),
        )


def ledger_corruption(repo: PostgresRepository, run: dict[str, Any], proof: str) -> None:
    ident = f"{run['id']}:e{run['retry_epoch']}:agent_model_request:1"
    with repo.transaction("alice") as connection:
        if proof == "ledger_missing":
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE owner='alice' AND kind='runtime_step' AND id=%s").format(
                    repo.table("core_entities")
                ),
                (ident,),
            )
            return
        row = repo.get("alice", "runtime_step", ident)
        data = dict(row["output"])
        if proof == "ledger_versions":
            data["versions"] = dict(data["versions"], **{"message:" + run["request"]["source_message_id"]: 99})
        else:
            data["role"] = "critic"
        connection.execute(
            sql.SQL(
                "UPDATE {} SET data=jsonb_set(jsonb_set(data,'{{output}}',%s),'{{output_sha256}}',%s) "
                "WHERE owner='alice' AND kind='runtime_step' AND id=%s"
            ).format(repo.table("core_entities")),
            (Jsonb(data), Jsonb(fingerprint(data)), ident),
        )


@pytest.mark.parametrize(
    "proof",
    [
        "pending_output",
        "pending_finished",
        "pending_usage",
        "pending_error",
        "pending_input",
        "pending_readonly",
        "missing_model",
        "old_epoch_model",
        "ledger_missing",
        "ledger_versions",
        "ledger_role",
        "operation_missing",
        "operation_wrong_id",
        "operation_digest",
        "operation_time",
        "entity_field",
        "entity_refs",
        "entity_subject",
        "mutation_input",
        "mutation_receipt",
        "external_revision",
        "source_withdrawal",
        "cancelled",
        "old_epoch",
    ],
)
def test_invalid_pending_proof_never_adopts_or_requests_another_model(
    pending_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, proof: str
) -> None:
    repo, intent = pending_repo, prepare_intent(pending_repo, "case_update")
    crash = CrashBeforeAcknowledgement(repo, intent.name, monkeypatch)
    with pytest.raises(SystemExit):
        invoke(repo, intent.run, ScriptedPort([answer("", [ToolCall("update", intent.name, intent.arguments)])]))
    assert crash.step is not None
    if proof == "external_revision":
        case = repo.get("alice", "case", intent.old["id"])
        repo.update("alice", "case", case["id"], {"title": "外部合成修订"}, expected_revision=case["revision"])
    elif proof == "source_withdrawal":
        with repo.transaction("alice") as connection:
            repo.revoke(connection, "alice", "message", intent.run["request"]["source_message_id"], "test-withdrawal")
    elif proof == "cancelled":
        modify(repo, intent.run, "cancel_requested_at=now()")
    elif proof != "old_epoch":
        corrupt(repo, intent.run, crash.step.seq, proof)
    modify(repo, intent.run, "lease_until=now()-interval '1 second'")
    if proof == "cancelled":
        with pytest.raises(CoreError):
            repo.claim_run("alice", intent.run["id"], lease_seconds=150)
        reclaimed = intent.run
    else:
        reclaimed = repo.claim_run("alice", intent.run["id"], lease_seconds=150)
    if proof == "old_epoch":
        modify(repo, intent.run, "retry_epoch=retry_epoch+1")
    before = business_state(repo)
    port = ScriptedPort([])
    with pytest.raises(CoreError):
        if proof == "old_epoch":
            AgentSnapshotStore(repo).load_or_build(reclaimed, lambda: pytest.fail("旧批次不能装配新上下文"))
        else:
            invoke(repo, reclaimed, port)
    assert port.requests == [] and business_state(repo) == before
    assert repo.fetch_run("alice", intent.run["id"])["result"] is None
    assert step_row(repo, crash.step)["status"] == "started"
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]


def test_snapshot_adopts_exact_pending_revision_without_ack_or_rewriting_frozen_bytes(
    pending_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, intent = pending_repo, prepare_intent(pending_repo, "case_update")
    crash = CrashBeforeAcknowledgement(repo, intent.name, monkeypatch)
    first = ScriptedPort([answer("", [ToolCall("update", intent.name, intent.arguments)])])
    with pytest.raises(SystemExit):
        invoke(repo, intent.run, first)
    assert crash.step is not None and crash.output is not None
    ident = f"{intent.run['id']}:e0:agent_initial_context"
    saved = repo.get("alice", "runtime_step", ident)
    before = business_state(repo)
    modify(repo, intent.run, "lease_until=now()-interval '1 second'")
    run = repo.claim_run("alice", intent.run["id"], lease_seconds=150)
    restored = AgentSnapshotStore(repo).load_or_build(run, lambda: pytest.fail("不能重建冻结上下文"))
    key = entity_dependency("case", intent.old["id"])
    assert restored.injected_versions[key] == intent.old["revision"]
    assert repo.fetch_run("alice", run["id"])["state_version"][key] == crash.output["receipt"]["revision"]
    step = step_row(repo, crash.step)
    assert (
        step["status"] == "started" and step["output"] is None and step["finished_at"] is None and step["usage"] == {}
    )
    AgentSnapshotStore(repo).load_or_build(repo.fetch_run("alice", run["id"]), lambda: pytest.fail("不能重建上下文"))
    assert repo.get("alice", "runtime_step", ident) == saved and business_state(repo) == before
    assert len(first.requests) == 1

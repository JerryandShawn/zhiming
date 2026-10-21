"""Synthetic inputs and real-PG observations for a committed-effect crash window."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.journal import Journal, JournalStep
from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import modify

BUSINESS_KINDS = ("fact", "note", "proposal", "case", "feedback", "followup", "reminder", "draw")
TEXTS = {
    "memory_write": "我喜欢合成的清淡口味",
    "note_write": "我在比较合成的两种学习安排",
    "memory_update": "更正：我喜欢早上阅读是记错了，我现在喜欢晚上阅读",
    "memory_update_proposal": "更正：我的存款现在是800元",
    "profile_update_request": "我想修改出生资料，请先向我核对",
    "case_update": "事项目标改成完成合成报告",
    "case_add_event": "我已经完成合成资料整理",
    "schedule_followup": "我在2026-11-01参加合成面试",
    "set_reminder": "提醒我2026-11-01 20:00开会",
}


@dataclass(frozen=True)
class EffectIntent:
    name: str
    run: dict[str, Any]
    arguments: dict[str, Any]
    old: dict[str, Any] | None = None


def queued(repo: PostgresRepository, text: str, case_ids: list[str]) -> dict[str, Any]:
    source = MemoryService(repo).receive(
        "alice", content=text, source_id=uuid.uuid4().hex, at=get_clock().now(), case_ids=case_ids
    )
    run = repo.queue_run(
        "alice",
        uuid.uuid4().hex,
        {"message": text, "source_message_id": source["id"], "case_ids": case_ids},
        case_ids=case_ids,
    )
    modify(repo, run, "runtime='v4',thread_id='life:self'")
    return repo.claim_run("alice", run["id"], lease_seconds=150)


def prepare_intent(repo: PostgresRepository, name: str) -> EffectIntent:
    memory, old = MemoryService(repo), None
    if name in {"memory_update", "memory_update_proposal"}:
        text = "我喜欢早上阅读" if name == "memory_update" else "请保存我的存款为500元"
        source = memory.receive("alice", content=text, source_id=uuid.uuid4().hex, at=get_clock().now())
        old = memory.save_fact(
            "alice", "self", source["id"], source["content"], "preference" if name == "memory_update" else "background"
        )
    elif name.startswith("case_"):
        old = memory.create_case("alice", "self", "合成事项", operation_id="effect-matrix-case")
    run = queued(repo, TEXTS[name], [old["id"]] if name.startswith("case_") else [])
    args = arguments(name, run, old)
    return EffectIntent("memory_update" if name == "memory_update_proposal" else name, run, args, old)


def arguments(name: str, run: dict[str, Any], old: dict[str, Any] | None) -> dict[str, Any]:
    request = run["request"]
    common = {"message_id": request["source_message_id"], "quote": request["message"]}
    if name == "memory_write":
        return dict(common, summary="合成清淡偏好", kind="preference")
    if name == "note_write":
        return {"source_ids": [common["message_id"]], "summary": "合成学习安排比较", "inferred": True}
    if name == "profile_update_request":
        return dict(common, fields=["birth.solar_datetime", "birth.timezone_offset"])
    if name in {"memory_update", "memory_update_proposal"}:
        assert old is not None
        return dict(common, fact_id=old["id"], expected_revision=old["revision"], summary="合成夜间阅读偏好")
    if name.startswith("case_"):
        assert old is not None
        base = {"id": old["id"], "expected_revision": old["revision"], "message_id": common["message_id"]}
        if name == "case_update":
            return dict(base, quote=common["quote"], changes={"goal": "完成合成报告"})
        return dict(base, kind="progress", content=common["quote"])
    due = dict(common, due_at="2026-11-01T20:00:00+08:00")
    return dict(due, text="开会") if name == "set_reminder" else dict(due, topic="合成面试", reason="事件后跟进")


class CrashBeforeAcknowledgement:
    def __init__(self, repo: PostgresRepository, name: str, monkeypatch: pytest.MonkeyPatch) -> None:
        self.repo, self.name, self.step, self.output = repo, name, None, None
        self.count = 0
        original = Journal.complete

        def intercept(journal: Journal, step: JournalStep, output: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            if step.kind == "tool" and step.name == self.name and self.count == 0:
                assert output.get("receipt", {}).get("id"), "crash injection requires an actual persisted effect"
                externally_committed(repo, step, output["receipt"])
                self.step, self.output = step, copy.deepcopy(output)
                self.count += 1
                raise SystemExit("synthetic-effect-committed-before-journal-ack")
            return original(journal, step, output, *args, **kwargs)

        monkeypatch.setattr(Journal, "complete", intercept)


def externally_committed(repo: PostgresRepository, step: JournalStep, receipt: dict[str, Any]) -> None:
    # A later acknowledgement transaction may exist; a separate connection must
    # already see the original effect and durable receipt before we interrupt it.
    with repo.pool.connection() as connection:
        mutation = connection.execute(
            sql.SQL("SELECT receipt FROM {} WHERE owner=%s AND operation=%s AND request_key=%s").format(
                repo.table("core_mutation_requests")
            ),
            (step.owner, "agent_" + step.name, step.operation_id),
        ).fetchone()
        entity = connection.execute(
            sql.SQL("SELECT revision FROM {} WHERE owner=%s AND kind=%s AND id=%s").format(repo.table("core_entities")),
            (step.owner, receipt["kind"], receipt["id"]),
        ).fetchone()
        operation = connection.execute(
            sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND left(operation_id,%s)=%s").format(
                repo.table("core_operations")
            ),
            (step.owner, len(step.operation_id) + 1, step.operation_id + ":"),
        ).fetchone()
    assert mutation and mutation["receipt"] == receipt
    assert entity and entity["revision"] == receipt["revision"] and operation


def business_state(repo: PostgresRepository) -> dict[str, list[dict[str, Any]]]:
    return {
        kind: sorted(repo.list("alice", kind, include_deleted=True), key=lambda row: row["id"])
        for kind in BUSINESS_KINDS
    }


def mutation_row(repo: PostgresRepository, step: JournalStep) -> dict[str, Any]:
    with repo.transaction() as connection:
        rows = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation=%s AND request_key=%s").format(
                repo.table("core_mutation_requests")
            ),
            ("alice", "agent_" + step.name, step.operation_id),
        ).fetchall()
    assert len(rows) == 1
    return rows[0]


def operation_rows(repo: PostgresRepository, step: JournalStep) -> list[dict[str, Any]]:
    with repo.transaction() as connection:
        return connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND left(operation_id,%s)=%s ORDER BY operation_id").format(
                repo.table("core_operations")
            ),
            ("alice", len(step.operation_id) + 1, step.operation_id + ":"),
        ).fetchall()


def step_row(repo: PostgresRepository, step: JournalStep) -> dict[str, Any]:
    with repo.transaction() as connection:
        return connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s").format(
                repo.table("core_run_steps")
            ),
            ("alice", step.run_id, step.epoch, step.seq),
        ).fetchone()


def assert_source_binding(repo: PostgresRepository, intent: EffectIntent, receipt: dict[str, Any]) -> None:
    entity = repo.get("alice", receipt["kind"], receipt["id"], include_deleted=True)
    assert entity["revision"] == receipt["revision"] and entity["subject_id"] == "self"
    refs = entity["source_refs"]
    source_id = intent.run["request"]["source_message_id"]
    assert any(ref["message_id"] == source_id and ref["version"] == 1 for ref in refs)
    if intent.name == "memory_update" and receipt["kind"] == "fact":
        assert entity["supersedes_id"] == intent.old["id"]
    if intent.name == "profile_update_request":
        assert entity["status"] == "pending" and entity["kind"] == "profile_update_request"
        assert MemoryService(repo).snapshot("alice")["profile"] == {}

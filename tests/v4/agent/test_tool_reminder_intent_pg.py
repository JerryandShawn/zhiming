"""Reminder intent cannot bypass the real leased source and PG mutation boundary."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.agent_tools_followups import execute_schedule
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_tool_interactions_pg import call
from .test_toolkit_pg import SAID_AT, Harness, setup
from .test_toolkit_pg import tool_repo as original_tool_repo


@pytest.fixture
def tool_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return original_tool_repo.__wrapped__(p2_repo, monkeypatch)


def arguments(harness: Harness, **changes: Any) -> dict[str, Any]:
    return {
        "message_id": harness.source["id"],
        "quote": harness.source["content"],
        "text": "开会",
        "due_at": "2026-10-21T09:00:00+08:00",
        **changes,
    }


def assert_no_effects(repo: PostgresRepository) -> None:
    assert repo.list("alice", "reminder") == repo.list("alice", "followup") == []
    with repo.transaction("alice") as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(repo.table("delivery_outbox"))
            ).fetchone()["n"]
            == 0
        )


@pytest.mark.parametrize(
    "text",
    [
        "2026-10-21 09:00不要提醒我开会",
        "2026-10-21 09:00别提醒我开会",
        "2026-10-21 09:00开会无需通知我",
        "2026-10-21 09:00开会不需要闹钟",
        "提醒我2026-10-21 09:00开会，但又不要提醒我",
        "假设我说提醒我2026-10-21 09:00开会",
        "同事说：提醒我2026-10-21 09:00开会",
        "他说“提醒我2026-10-21 09:00开会”",
    ],
)
def test_negated_reported_hypothetical_or_conflicting_source_never_creates_reminder(
    tool_repo: PostgresRepository, text: str
) -> None:
    harness = setup(tool_repo, text)
    result, _ = call(harness, "set_reminder", arguments(harness))
    assert not result.ok
    assert_no_effects(tool_repo)
    assert tool_repo.fetch_run("alice", harness.run["id"])["calls"] == 0


def test_cropped_quote_cannot_remove_source_negation(tool_repo: PostgresRepository) -> None:
    harness = setup(tool_repo, "不要提醒我2026-10-21 09:00开会")
    result, _ = call(harness, "set_reminder", arguments(harness, quote="提醒我2026-10-21 09:00开会"))
    assert not result.ok
    assert_no_effects(tool_repo)


@pytest.mark.parametrize(
    "text", ["别忘了提醒我2026-10-21 09:00开会", "请在2026-10-21 09:00通知我开会", "给我设个2026-10-21 09:00开会闹钟"]
)
def test_explicit_positive_reminders_survive_proactive_optout(tool_repo: PostgresRepository, text: str) -> None:
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=jsonb_set(settings,'{{proactive_followups_enabled}}','false')").format(
                tool_repo.table("core_owners")
            )
        )
    harness = setup(tool_repo, text)
    result, _ = call(harness, "set_reminder", arguments(harness))
    assert result.ok and len(tool_repo.list("alice", "reminder")) == 1
    row = tool_repo.get("alice", "reminder", result.receipt["id"])
    assert row["source_refs"][0]["quote"] == text and row["explicit"] is True
    assert row["due_at"] == "2026-10-21T01:00:00+00:00"


def source_fact(repo: PostgresRepository) -> dict[str, Any]:
    memory = MemoryService(repo)
    source = memory.receive("alice", content="我喜欢蓝色", source_id=uuid.uuid4().hex, at=SAID_AT)
    fact = memory.save_fact("alice", "self", source["id"], source["content"], "preference")
    assert fact["write_status"] == "saved"
    return fact


def followup_arguments(harness: Harness, ident: str) -> dict[str, Any]:
    return {
        "message_id": harness.source["id"],
        "quote": harness.source["content"],
        "topic": "开会",
        "reason": "合成跟进",
        "due_at": "2026-10-21T09:00:00+08:00",
        "source_fact_id": ident,
    }


def test_fact_revocation_ledger_blocks_active_row_with_unchanged_refs(tool_repo: PostgresRepository) -> None:
    fact = source_fact(tool_repo)
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(connection, "alice", "fact", fact["id"], "stopped")
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "active"
    harness = setup(tool_repo, "提醒我2026-10-21 09:00开会")
    with pytest.raises((EvidenceError, ScopeError)):
        call(harness, "schedule_followup", followup_arguments(harness, fact["id"]))
    assert_no_effects(tool_repo)


def test_fact_revocation_is_rechecked_before_cached_receipt(tool_repo: PostgresRepository) -> None:
    fact = source_fact(tool_repo)
    harness = setup(tool_repo, "提醒我2026-10-21 09:00开会")
    result, context = call(harness, "schedule_followup", followup_arguments(harness, fact["id"]))
    assert result.ok
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(connection, "alice", "fact", fact["id"], "stopped")
    with pytest.raises((EvidenceError, ScopeError)):
        execute_schedule(harness.service, "schedule_followup", followup_arguments(harness, fact["id"]), context)
    assert len(tool_repo.list("alice", "followup")) == 1


def test_real_memory_retirement_cannot_create_new_reminder_from_old_fact(tool_repo: PostgresRepository) -> None:
    fact = source_fact(tool_repo)
    MemoryService(tool_repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"], operation="stop")
    harness = setup(tool_repo, "提醒我2026-10-21 09:00开会")
    with pytest.raises((EvidenceError, ScopeError)):
        call(harness, "schedule_followup", followup_arguments(harness, fact["id"]))
    assert_no_effects(tool_repo)

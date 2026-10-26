"""A sensitive conflict grants once, and undo restores settings and dependent facts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.memory2_proposals import MemoryProposalService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.timekit.clock import get_clock

from .test_memory2_conflict_resolution_pg import NOW, choose, undo
from .test_memory2_conflict_resolution_pg import resolution_repo as base_resolution_repo
from .test_toolkit_pg import setup


@pytest.fixture(name="tool_repo")
def conflict_category_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return base_resolution_repo.__wrapped__(p2_repo, monkeypatch)


def sensitive_conflict(repo: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, dict, Any]:
    first = setup(repo, "我喜欢合成复诊")
    pending, _, _ = first.write("preference")
    assert pending.receipt["write_status"] == "pending_confirmation"
    action = first.service.memory.receive(
        "alice", content="请保存这条记忆", source_id="synthetic-first-sensitive-accept", channel="synthetic"
    )
    accepted = MemoryProposalService(first.service.memory).accept(
        "alice",
        "self",
        pending.receipt["id"],
        expected_revision=1,
        message_id=action["id"],
        remember_category=False,
        operation_id="synthetic-first-sensitive-accept",
    )
    old = repo.get("alice", "fact", accepted["fact_id"])
    first.finish()
    monkeypatch.setattr("tests.v4.agent.test_toolkit_pg.SAID_AT", NOW)
    current = setup(repo, "我不喜欢合成复诊")
    result, _, _ = current.write("preference")
    assert result.receipt["code"] == "memory2_possible_conflict"
    assert result.data["possible_conflict"]["sensitive"] is True
    assert "敏感信息" in result.data["possible_conflict"]["summary"]
    return current, old, result


def patch_settings(repo: Any, **changes: Any) -> None:
    settings = dict(repo.assert_scope("alice")["settings"], **changes)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(repo.table("core_owners")),
            (Jsonb(settings), "alice"),
        )
        repo.bump_revision(connection, "alice", owner_scope=True)


def test_category_choice_and_dependent_auto_saves_are_revoked_by_one_undo(
    tool_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    h, old, pending = sensitive_conflict(tool_repo, monkeypatch)
    before = tool_repo.assert_scope("alice")["settings"]
    selected = choose(h, pending, remember=True)
    new = tool_repo.get("alice", "fact", selected["fact_id"])
    settings = tool_repo.assert_scope("alice")["settings"]
    assert settings["auto_save_categories"] == ["health"]
    assert settings["memory_category_authorizations"]["health"] == new["approval_consent_id"]
    h.finish()
    get_clock().advance(timedelta(minutes=30))
    monkeypatch.setattr("tests.v4.agent.test_toolkit_pg.SAID_AT", get_clock().now())
    future = setup(tool_repo, "我最近失眠，准备调整作息")
    saved, _, _ = future.write("background")
    assert saved.ok and saved.receipt["write_status"] == "saved"
    future_fact = tool_repo.get("alice", "fact", saved.receipt["fact_id"])
    assert new["approval_consent_id"] in future_fact["category_consent_ids"]
    future.finish()
    patch_settings(tool_repo, runtime="v4", synthetic_setting="keep")
    restored = undo(h, pending)
    assert set(restored["affected_ids"]) == {new["id"], future_fact["id"]}
    actual = tool_repo.assert_scope("alice")["settings"]
    assert {key: value for key, value in actual.items() if key not in {"runtime", "synthetic_setting"}} == before
    assert actual["runtime"] == "v4" and actual["synthetic_setting"] == "keep"
    assert [row["id"] for row in h.service.memory.facts("alice")] == [old["id"]]
    assert tool_repo.get("alice", "fact", future_fact["id"])["status"] == "retired"
    again = setup(tool_repo, "我最近失眠，需要慢慢调整")
    result, _, _ = again.write("background")
    assert result.receipt["write_status"] == "pending_confirmation"


def test_later_category_edits_block_undo_without_revoking_other_decisions(
    tool_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    h, _, pending = sensitive_conflict(tool_repo, monkeypatch)
    selected = choose(h, pending, remember=True)
    patch_settings(tool_repo, auto_save_categories=["health", "money"])
    with pytest.raises(RevisionConflict, match="分类授权"):
        undo(h, pending)
    assert tool_repo.get("alice", "fact", selected["fact_id"])["status"] == "active"
    assert tool_repo.assert_scope("alice")["settings"]["auto_save_categories"] == ["health", "money"]


def test_ordinary_conflict_cannot_create_sensitive_category_grants(tool_repo: Any) -> None:
    from .test_memory2_conflicts_pg import conflict

    h, old, pending, _, _ = conflict(tool_repo)
    with pytest.raises(EvidenceError, match="普通偏好"):
        choose(h, pending, remember=True)
    assert tool_repo.list("alice", "consent") == []
    assert [row["id"] for row in tool_repo.list("alice", "fact")] == [old["id"]]
    assert "auto_save_categories" not in tool_repo.assert_scope("alice")["settings"]

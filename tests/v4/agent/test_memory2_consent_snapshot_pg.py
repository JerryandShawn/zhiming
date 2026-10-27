"""Request-only consent memo, interval evidence and explicit invalidation notice."""

from time import perf_counter
from typing import Any

import pytest

from mingjing_core.application.memory2_consent import categories_granted, consent_live

from .test_memory2_proposals_pg import confirm
from .test_memory2_slots_pg import slots_repo
from .test_toolkit_pg import setup


@pytest.fixture(name="tool_repo")
def snapshot_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return slots_repo.__wrapped__(p2_repo, monkeypatch)


def approved_interval(repo):
    h = setup(repo, "我最近失眠。合成旁支信息")
    pending, _, _ = h.write("background", quote="我最近失眠")
    receipt = confirm(repo, pending.receipt["id"], remember=True)
    fact = repo.get("alice", "fact", receipt["fact_id"])
    proof = repo.get("alice", "consent", fact["approval_consent_id"])
    h.finish()
    return h.service.memory, fact, proof


def test_other_interval_revocation_keeps_authorized_health_quote_live(tool_repo):
    memory, fact, proof = approved_interval(tool_repo)
    original = memory.get_source("alice", proof["message_id"])
    start = original["content"].index("合成旁支")
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(
            connection,
            "alice",
            "source_span",
            "unrelated",
            "deleted",
            {"message_id": original["id"], "start": start, "end": len(original["content"])},
        )
        tool_repo.update("alice", "message", original["id"], {"redacted": True}, expected_revision=original["revision"])
    assert consent_live(memory, "alice", "self", proof)
    assert categories_granted(memory, "alice", "self", ("health",))
    assert fact["id"] in {row["id"] for row in memory.facts("alice")}
    assert not tool_repo.list("alice", "knowledge_gap")


def test_changed_authorized_quote_is_hidden_and_emits_one_body_free_notice(tool_repo):
    memory, fact, proof = approved_interval(tool_repo)
    original = memory.get_source("alice", proof["message_id"])
    tool_repo.update(
        "alice",
        "message",
        original["id"],
        {"content": original["content"].replace("失眠", "早睡")},
        expected_revision=original["revision"],
    )
    assert not consent_live(memory, "alice", "self", proof)
    assert fact["id"] not in {row["id"] for row in memory.facts("alice")}
    notes = tool_repo.list("alice", "knowledge_gap")
    assert len(notes) == 1 and notes[0]["kind"] == "memory_authority_notice"
    assert "失眠" not in str(notes) and not notes[0].get("source_refs")
    revision = tool_repo.get_revision("alice")
    memory.facts("alice")
    assert tool_repo.get_revision("alice") == revision


def test_legacy_consent_uses_frozen_proposal_quote_when_whole_revision_changes(tool_repo):
    memory, _, proof = approved_interval(tool_repo)
    payload = {
        key: value
        for key, value in proof.items()
        if key
        not in {"id", "owner", "revision", "created_at", "updated_at", "source_quote_hash", "approval_quote_hash"}
    }
    legacy = tool_repo.put("alice", "consent", proof["id"], payload, expected_revision=proof["revision"])
    original = memory.get_source("alice", proof["message_id"])
    tool_repo.update("alice", "message", original["id"], {"redacted": True}, expected_revision=original["revision"])
    assert consent_live(memory, "alice", "self", legacy)


def test_500_facts_200_revocations_use_one_ledger_read_and_no_cross_request_cache(tool_repo, monkeypatch):
    memory, fact, proof = approved_interval(tool_repo)
    reserved = {"id", "owner", "revision", "created_at", "updated_at"}
    payload = {key: value for key, value in fact.items() if key not in reserved}
    with tool_repo.transaction("alice") as connection:
        for index in range(499):
            tool_repo.put("alice", "fact", f"load-{index}", payload, expected_revision=0)
        for index in range(200):
            tool_repo.revoke(connection, "alice", "fact", f"unrelated-{index}", "deleted")
    original = tool_repo.revocations
    calls = []

    def observed(owner):
        calls.append(owner)
        return original(owner)

    monkeypatch.setattr(tool_repo, "revocations", observed)
    started = perf_counter()
    assert len(memory.facts("alice")) == 500
    assert perf_counter() - started < 5 and calls == ["alice"]
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(connection, "alice", "consent", proof["id"], "stopped")
    assert memory.facts("alice") == [] and calls == ["alice", "alice"]

"""P5 consent records remain live authority for reads and frozen context dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest

from mingjing_core.application.agent_commit_versions import RegenerationRequired, assert_no_withdrawal
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock

from .test_agent_runtime_pg import invoke, queued
from .test_context_epochs_pg import ContextEpochService, finish_component, started
from .test_context_pg import build
from .test_loop_cycle_support import ScriptedPort, answer
from .test_memory2_proposals_pg import confirm, pending
from .test_memory2_proposals_pg import proposal_repo as base_proposal_repo


@pytest.fixture(name="tool_repo")
def consent_read_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    previous = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat("2026-10-24T05:00:00+08:00")))
    try:
        yield base_proposal_repo.__wrapped__(p2_repo, monkeypatch)
    finally:
        set_clock(previous)


def approved(repo: Any, *, category: bool = False) -> tuple[Any, dict, dict]:
    harness, ident = pending(repo)
    receipt = confirm(repo, ident, remember=category)
    fact = repo.get("alice", "fact", receipt["fact_id"])
    proof = repo.get("alice", "consent", fact["approval_consent_id"])
    harness.finish()
    return harness, fact, proof


@pytest.mark.parametrize("change", ["stop", "delete", "ledger"])
def test_revoked_proof_hides_fact_from_real_memory_query_without_rewriting_fact(tool_repo: Any, change: str) -> None:
    _, before, proof = approved(tool_repo)
    if change == "stop":
        tool_repo.update("alice", "consent", proof["id"], {"status": "stopped"}, expected_revision=proof["revision"])
    elif change == "delete":
        tool_repo.delete("alice", "consent", proof["id"], expected_revision=proof["revision"])
    else:
        with tool_repo.transaction("alice") as connection:
            tool_repo.revoke(connection, "alice", "consent", proof["id"], "stopped")
    memory = MemoryService(tool_repo)
    assert before["id"] not in {row["id"] for row in memory.facts("alice")}
    assert tool_repo.get("alice", "fact", before["id"]) == before
    assert before["id"] in {row["id"] for row in memory.facts("alice", include_inactive=True)}


def test_injected_fact_carries_exact_consent_version_and_new_read_hides_stopped_proof(tool_repo: Any) -> None:
    harness, fact, proof = approved(tool_repo)
    current = harness.service.memory.receive("alice", content="合成当前健康问题", source_id="consent-query")
    frozen = build(harness.service.memory, current)
    key = entity_dependency("consent", proof["id"])
    assert frozen.injected_versions[key] == proof["revision"]
    tool_repo.update("alice", "consent", proof["id"], {"status": "stopped"}, expected_revision=proof["revision"])
    assert not tool_repo.verify_versions("alice", frozen.injected_versions)
    clean = build(harness.service.memory, current)
    assert fact["id"] not in {row["id"] for row in clean.alias_map.values()}
    assert key not in clean.injected_versions


def test_category_saved_followup_also_requires_live_proof(tool_repo: Any) -> None:
    harness, _, proof = approved(tool_repo, category=True)
    from .test_toolkit_pg import setup

    followup = setup(tool_repo, "我这周复诊了")
    result, _, _ = followup.write("background")
    fact = tool_repo.get("alice", "fact", result.receipt["fact_id"])
    assert fact["category_consent_ids"] == [proof["id"]]
    followup.finish()
    tool_repo.delete("alice", "consent", proof["id"], expected_revision=proof["revision"])
    assert harness.service.memory.facts("alice") == []


@pytest.mark.parametrize(
    "bad",
    [
        {"category_consent_ids": "bad"},
        {"category_consent_ids": [None]},
        {"approval_consent_id": None},
        {"approval_consent_id": "missing-consent"},
    ],
)
def test_malformed_or_missing_consent_does_not_fall_back_to_granted_flag(tool_repo: Any, bad: dict) -> None:
    harness, fact, _ = approved(tool_repo)
    tool_repo.update("alice", "fact", fact["id"], bad, expected_revision=fact["revision"])
    assert harness.service.memory.facts("alice") == []


def test_stopped_proof_rejects_native_frozen_send_without_changing_send_gate(tool_repo: Any) -> None:
    harness, _, proof = approved(tool_repo)
    current = harness.service.memory.receive("alice", content="合成当前问题", source_id="frozen-consent-send")
    frozen = build(harness.service.memory, current)
    step = started(harness.service.memory, current, frozen, "frozen-consent-send")
    tool_repo.update("alice", "consent", proof["id"], {"status": "stopped"}, expected_revision=proof["revision"])
    with pytest.raises(RevisionConflict):
        ContextEpochService(tool_repo).mark_sent(step, frozen)
    finish_component(harness.service.memory, step)


def test_live_consent_dependency_passes_actual_scripted_agent_final_commit(tool_repo: Any) -> None:
    _, _, proof = approved(tool_repo)
    run = queued(tool_repo, "我的合成健康情况是什么")
    result, events = invoke(tool_repo, run, ScriptedPort([answer("你提到最近在吃药〔f1〕")]))
    assert result["text"] == "你提到最近在吃药〔f1〕" and events[-1]["type"] == "final"
    stored = tool_repo.fetch_run("alice", run["id"])
    assert stored["status"] == "succeeded"
    assert stored["state_version"][entity_dependency("consent", proof["id"])] == proof["revision"]


def test_ledger_revocation_during_model_response_is_fenced_by_native_final_guard(tool_repo: Any) -> None:
    _, _, proof = approved(tool_repo)

    class RevokingPort(ScriptedPort):
        def stream(self, messages: Any, **kwargs: Any) -> Iterator[Any]:
            if not self.requests:
                with tool_repo.transaction("alice") as connection:
                    tool_repo.revoke(connection, "alice", "consent", proof["id"], "stopped")
            yield from super().stream(messages, **kwargs)

    run = queued(tool_repo, "合成有效记忆问题")
    port = RevokingPort([answer("过期答案候选〔f1〕"), answer("请以当前有效依据为准")])
    try:
        result, _ = invoke(tool_repo, run, port)
    except (EvidenceError, RevisionConflict):
        result = None
    assert len(port.requests) >= 1
    assert result is None or result["text"] != "过期答案候选〔f1〕"
    messages = [row for row in tool_repo.list("alice", "message") if row.get("run_id") == run["id"]]
    assert all(row.get("content") != "过期答案候选〔f1〕" for row in messages)


def test_ledger_only_revocation_is_rejected_at_both_native_freshness_checks(tool_repo: Any) -> None:
    harness, _, proof = approved(tool_repo)
    current = harness.service.memory.receive("alice", content="合成账本检查", source_id="ledger-only-consent")
    frozen = build(harness.service.memory, current)
    step = started(harness.service.memory, current, frozen, "ledger-only-consent")
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(connection, "alice", "consent", proof["id"], "stopped")
    # A ledger-only withdrawal intentionally leaves the entity revision intact.
    assert tool_repo.verify_versions("alice", frozen.injected_versions)
    with pytest.raises(RegenerationRequired):
        ContextEpochService(tool_repo).mark_sent(step, frozen)
    with pytest.raises(RegenerationRequired):
        assert_no_withdrawal(
            tool_repo, tool_repo.fetch_run("alice", step.run_id), frozen.injected_versions, frozen.snapshot_revision
        )
    finish_component(harness.service.memory, step)

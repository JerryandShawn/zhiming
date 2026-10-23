"""Confirmed profiles enter actual L2, with original facts and approval in its version closure."""

from __future__ import annotations

from typing import Any

import pytest

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.context_epochs import ContextEpochService
from mingjing_core.application.memory2_profile_reflection import (
    ProfileReflectionService,
)

from .test_agent_runtime_pg import invoke, queued
from .test_context_epochs_pg import finish_component, started
from .test_context_pg import build
from .test_loop_cycle_support import ScriptedPort, answer
from .test_memory2_profile_proposals_pg import act, candidate
from .test_memory2_slots_pg import fact
from .test_memory2_slots_pg import slots_repo as base_slots_repo


@pytest.fixture(name="tool_repo")
def profile_context_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return base_slots_repo.__wrapped__(p2_repo, monkeypatch)


def profile_ids(result: Any) -> set[str]:
    return {row["id"] for row in result.alias_map.values() if row["kind"] == "profile_doc"}


def test_pending_not_injected_then_confirmed_profile_enters_l2_with_original_closure(tool_repo: Any) -> None:
    proposal, fact = candidate(tool_repo)
    memory = V4FactMemory(tool_repo)
    current = memory.receive("alice", content="合成现在问题", source_id="synthetic-before-profile", channel="synthetic")
    assert profile_ids(build(memory, current)) == set()
    accepted = act(tool_repo, proposal)
    current = memory.receive("alice", content="合成现在问题", source_id="synthetic-after-profile", channel="synthetic")
    result = build(memory, current)
    assert profile_ids(result) == {accepted["id"]}
    assert result.injected_versions["profile_doc:" + accepted["id"]] == accepted["revision"]
    assert result.injected_versions["fact:" + fact["id"]] == fact["revision"]
    item = tool_repo.get("alice", "profile_doc", accepted["id"])
    for ref in item["source_refs"]:
        assert result.injected_versions["message:" + ref["message_id"]] == ref["version"]
    l2 = next(layer for layer in result.budget.layers if layer.name == "L2")
    text = "\n".join(str(message.content) for item in l2.items for message in item.messages)
    assert '"confirmed_by_user":true' in text and "偏好合成徒步" in text
    assert len(l2.items) == 1


def test_later_fact_revision_hides_stale_profile_and_falls_back_to_current_fact(tool_repo: Any) -> None:
    proposal, fact = candidate(tool_repo)
    accepted = act(tool_repo, proposal)
    tool_repo.update("alice", "fact", fact["id"], {"summary": "合成已变"}, expected_revision=fact["revision"])
    memory = V4FactMemory(tool_repo)
    current = memory.receive(
        "alice", content="合成问题", source_id="synthetic-stale-profile-query", channel="synthetic"
    )
    result = build(memory, current)
    assert accepted["id"] not in profile_ids(result)
    assert any(value["id"] == fact["id"] for value in result.alias_map.values())


def test_undo_removes_profile_from_actual_context_and_preserves_source_fact(tool_repo: Any) -> None:
    proposal, fact = candidate(tool_repo)
    accepted = act(tool_repo, proposal)
    resolved = tool_repo.get("alice", "proposal", proposal["id"])
    act(tool_repo, resolved, "undo", key="synthetic-context-profile-undo")
    memory = V4FactMemory(tool_repo)
    current = memory.receive("alice", content="合成问题", source_id="synthetic-profile-undo-query", channel="synthetic")
    result = build(memory, current)
    assert accepted["id"] not in profile_ids(result)
    assert any(value["id"] == fact["id"] for value in result.alias_map.values())


def test_accepted_profile_changes_prefix_without_rewriting_l5_epoch(tool_repo: Any) -> None:
    proposal, _ = candidate(tool_repo)
    memory = V4FactMemory(tool_repo)
    first_source = memory.receive(
        "alice", content="合成问题", source_id="synthetic-profile-cache-first", channel="synthetic"
    )
    first = build(memory, first_source)
    step = started(memory, first_source, first, "synthetic-profile-cache-first")
    ContextEpochService(tool_repo).mark_sent(step, first)
    finish_component(memory, step)
    accepted = act(tool_repo, proposal)
    source = memory.receive(
        "alice", content="合成后续问题", source_id="synthetic-profile-cache-next", channel="synthetic"
    )
    current = build(memory, source)
    assert accepted["id"] in profile_ids(current)
    assert current.cache_epoch.stable_sha256 != first.cache_epoch.stable_sha256
    assert current.cache_epoch.prefix_sha256 != first.cache_epoch.prefix_sha256
    assert current.cache_epoch.epoch == first.cache_epoch.epoch
    step = started(memory, source, current, "synthetic-profile-cache-next")
    receipt = ContextEpochService(tool_repo).mark_sent(step, current)
    assert receipt["generation"] == 2 and receipt["prefix_sha256"] == current.cache_epoch.prefix_sha256
    finish_component(memory, step)


def test_confirmed_profile_alias_passes_actual_scripted_agent_final_commit(tool_repo: Any) -> None:
    proposal, _ = candidate(tool_repo)
    accepted = act(tool_repo, proposal)
    run = queued(tool_repo, "我有哪些合成偏好？")
    port = ScriptedPort([answer("你偏好合成徒步〔p1〕")])
    result, events = invoke(tool_repo, run, port)
    assert result["text"] == "你偏好合成徒步〔p1〕"
    assert tool_repo.fetch_run("alice", run["id"])["status"] == "succeeded"
    assert events[-1]["type"] == "final" and len(port.requests) == 1
    assert "偏好合成徒步" in "\n".join(str(message.content) for message in port.requests[0]["messages"])
    assert tool_repo.get("alice", "profile_doc", accepted["id"])["confirmed_by_user"] is True


def test_profile_summary_cannot_hide_a_hard_user_constraint(tool_repo: Any) -> None:
    row = fact(tool_repo, "我不能上合成夜班", "2026-10-17T10:00:00+08:00", kind="constraint")
    memory = V4FactMemory(tool_repo)
    receipt = ProfileReflectionService(memory).propose(
        "alice",
        "self",
        [{"section": 3, "text": "希望合成稳定作息", "fact_ids": [row["id"]]}],
        fact_versions={row["id"]: row["revision"]},
        operation_id="synthetic-profile-constraint",
    )
    act(tool_repo, tool_repo.get("alice", "proposal", receipt["ids"][0]))
    source = memory.receive(
        "alice", content="合成问题", source_id="synthetic-profile-constraint-query", channel="synthetic"
    )
    result = build(memory, source)
    l2 = next(layer for layer in result.budget.layers if layer.name == "L2")
    text = "\n".join(str(message.content) for item in l2.items for message in item.messages)
    assert "我不能上合成夜班" in text and "希望合成稳定作息" in text

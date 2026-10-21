"""Case indexes cite real scoped rows without expanding selected-case authority."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from typing import Any

import pytest

from mingjing_core.agent.journal import Journal
from mingjing_core.agent.loop_codec import extend_aliases, tool_message, verified_versions
from mingjing_core.agent.toolkit import ToolContext, ToolRegistry
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_thread_inbox_pg import ingress, set_runtime, submit
from .test_toolkit_pg import Harness, setup


@pytest.fixture(name="index_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def existing_case(repo: PostgresRepository) -> tuple[dict[str, Any], dict[str, Any]]:
    memory = MemoryService(repo)
    source = memory.receive("alice", content="未选择事项中的合成目标正文", source_id="case-original")
    case = memory.create_case("alice", "self", "合成索引事项", goal=source["content"], message_id=source["id"])
    memory.receive("alice", content=source["content"], source_id="case-original", case_ids=[case["id"]])
    return case, source


def index_step(h: Harness) -> tuple[Any, Any]:
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="case_list", input_fp=h.registry.fingerprint("case_list", {})
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    return step, h.registry.execute("case_list", {}, ctx)


def test_completed_index_registers_case_only_without_unselected_source_closure(index_repo: PostgresRepository) -> None:
    case, source = existing_case(index_repo)
    h = setup(index_repo, "那件事的进展如何")
    step, result = index_step(h)
    with pytest.raises(EvidenceError, match="已完成"):
        verified_versions(h.service, h.run, "case_list", result)
    h.journal.complete(step, result.model_dump())
    versions, records = verified_versions(h.service, h.run, "case_list", result)
    assert versions == {entity_dependency("case", case["id"]): case["revision"]}
    assert "message:" + source["id"] not in versions
    assert records[0]["kind"] == "case" and records[0]["basis"] == "case_index" and records[0]["index_only"]
    assert case["state"]["goal"] not in str(result.model_dump()) and source["content"] not in str(records)


@pytest.mark.parametrize("tampering", ["title", "revision", "id", "professional_alias"])
def test_model_or_result_tampering_cannot_register_index(index_repo: PostgresRepository, tampering: str) -> None:
    existing_case(index_repo)
    h = setup(index_repo, "那件事的进展如何")
    step, result = index_step(h)
    h.journal.complete(step, result.model_dump())
    forged = result.model_copy(deep=True)
    if tampering == "professional_alias":
        forged.data["persisted"] = {"artifacts": [{"id": "fake", "native_id": "fake", "revision": 1}], "claims": []}
    else:
        forged.data["cases"][0][tampering] = {"title": "伪造标题", "revision": 99, "id": "foreign"}[tampering]
    with pytest.raises(EvidenceError):
        verified_versions(h.service, h.run, "case_list", forged)


@pytest.mark.parametrize("change", ["cross_owner", "old_epoch", "case_revision", "case_deleted"])
def test_scope_epoch_and_current_pg_index_are_rechecked(index_repo: PostgresRepository, change: str) -> None:
    case, _ = existing_case(index_repo)
    h = setup(index_repo, "那件事的进展如何")
    step, result = index_step(h)
    h.journal.complete(step, result.model_dump())
    run = copy.deepcopy(h.run)
    if change == "cross_owner":
        run["owner"] = "bob"
    elif change == "old_epoch":
        run["retry_epoch"] += 1
    elif change == "case_revision":
        index_repo.update("alice", "case", case["id"], {"title": "新的真实标题"}, expected_revision=case["revision"])
    else:
        index_repo.delete("alice", "case", case["id"], expected_revision=case["revision"])
    with pytest.raises((EvidenceError, LeaseConflict, ScopeError)):
        verified_versions(h.service, run, "case_list", result)


def test_repeated_identical_index_steps_reuse_one_alias(index_repo: PostgresRepository) -> None:
    existing_case(index_repo)
    h, aliases = setup(index_repo, "那件事的进展如何"), {}
    for _ in range(2):
        step, result = index_step(h)
        h.journal.complete(step, result.model_dump())
        _, records = verified_versions(h.service, h.run, "case_list", result)
        extend_aliases(aliases, records)
    assert list(aliases) == ["e1"] and len(index_repo.list("alice", "case")) == 1


def test_source_withdrawal_invalidates_real_case_index(index_repo: PostgresRepository) -> None:
    case, source = existing_case(index_repo)
    h = setup(index_repo, "那件事的进展如何")
    step, result = index_step(h)
    h.journal.complete(step, result.model_dump())
    memory = MemoryService(index_repo)
    fact = memory.save_fact("alice", "self", source["id"], source["content"], "preference")
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    redacted = index_repo.get("alice", "case", case["id"])
    assert redacted["revision"] > case["revision"] and redacted["state"]["goal"] == "" and redacted["source_refs"] == []
    with pytest.raises(EvidenceError):
        verified_versions(h.service, h.run, "case_list", result)


def test_self_reported_alias_metadata_is_not_projected(index_repo: PostgresRepository) -> None:
    case, _ = existing_case(index_repo)
    h = setup(index_repo, "那件事的进展如何")
    step, result = index_step(h)
    h.journal.complete(step, result.model_dump())
    forged = result.model_copy(deep=True)
    forged.data.update(
        registered_aliases={"e99": {"kind": "case", "id": case["id"], "revision": case["revision"]}},
        alias_registration="verified_current_run",
    )
    with pytest.raises(EvidenceError):
        verified_versions(h.service, h.run, "case_list", forged)
    projected = json.loads(tool_message("fake", forged, "cycle", aliases={}).content)
    assert "registered_aliases" not in projected["data"] and "alias_registration" not in projected["data"]


def test_runtime_can_cite_unselected_index_but_cannot_modify_that_case(index_repo: PostgresRepository) -> None:
    case, _ = existing_case(index_repo)
    set_runtime(index_repo, "v4")
    intake, thread = ingress(index_repo)
    parent = index_repo.claim_run("alice", submit(intake, thread, "那件事的进展，目标改成合成新计划")["id"])
    write = {
        "id": case["id"],
        "expected_revision": case["revision"],
        "message_id": parent["request"]["source_message_id"],
        "quote": parent["request"]["message"],
        "changes": {"goal": "合成新计划"},
    }
    port = ScriptedPort(
        [
            answer("", [ToolCall("index", "case_list", {})]),
            answer("", [ToolCall("must-not-edit", "case_update", write)]),
            answer("已看到这个事项索引〔e1〕"),
        ]
    )
    result = AgentRuntime(index_repo, port, SyntheticMeter(), offline=True).execute(
        intake.service, "alice", parent["id"], parent["lease_token"]
    )
    assert "〔e1〕" in result["text"] and result["meta"]["case_ids"] == []
    assert result["used_fact_ids"] == [] and result["used_claim_ids"] == []
    current = index_repo.fetch_run("alice", parent["id"])
    assert entity_dependency("case", case["id"]) in current["state_version"]
    assert index_repo.get("alice", "case", case["id"])["revision"] == case["revision"]
    tool_messages = [message for message in port.requests[-1]["messages"] if message.role == "tool"]
    assert any("registered_aliases" in message.content and "case_index" in message.content for message in tool_messages)
    assert any("AUTH_SCOPE_ERROR" in message.content for message in tool_messages)


def test_private_run_cannot_register_long_term_case_index(index_repo: PostgresRepository) -> None:
    existing_case(index_repo)
    set_runtime(index_repo, "v4")
    intake, thread = ingress(index_repo, private=True)
    run = index_repo.claim_run("alice", submit(intake, thread, "合成私密讨论")["id"])
    registry, journal = ToolRegistry(AgentToolsService(index_repo)), Journal(index_repo, "alice")
    step = journal.next_or_replay(run, kind="tool", name="case_list", input_fp=registry.fingerprint("case_list", {}))
    ctx = ToolContext.from_step(
        step, thread_id=thread, incognito=True, source_ids=(run["request"]["source_message_id"],)
    )
    result = registry.execute("case_list", {}, ctx)
    journal.complete(step, result.model_dump())
    assert not result.ok and result.data["code"] == "tool_unavailable"
    assert verified_versions(registry.service, run, "case_list", result) == ({}, [])
    direct = journal.next_or_replay(run, kind="tool", name="case_list", input_fp=registry.fingerprint("case_list", {}))
    ctx = ToolContext.from_step(
        direct, thread_id=thread, incognito=True, source_ids=(run["request"]["source_message_id"],)
    )
    result = registry.service.execute("case_list", {}, ctx)
    assert result.ok
    journal.complete(direct, result.model_dump())
    with pytest.raises(ScopeError, match="无痕"):
        verified_versions(registry.service, run, "case_list", result)

"""Real case mutation component precedes an independent Runtime index query."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from mingjing_core.agent.journal import Journal
from mingjing_core.agent.toolkit import ToolContext, ToolRegistry
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository

from .test_case_index_lineage_pg import existing_case
from .test_historical_case_index_guards_pg import assert_unpublished, finish
from .test_historical_case_index_pg import prepared_history
from .test_loop_cycle_case_versions_pg import selected_run
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_thread_inbox_pg import ingress, set_runtime, submit


@pytest.fixture(name="lifecycle_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def legal_mutation_component(repo: PostgresRepository, status: str) -> tuple[dict[str, Any], dict[str, Any]]:
    case, original = existing_case(repo)
    text = "请将合成事项暂停" if status == "paused" else "请将合成事项关闭"
    run = selected_run(repo, case["id"], text)
    registry, journal = ToolRegistry(AgentToolsService(repo)), Journal(repo, "alice")
    arguments = {
        "id": case["id"],
        "expected_revision": case["revision"],
        "message_id": run["request"]["source_message_id"],
        "quote": text,
        "changes": {"status": status},
    }
    step = journal.next_or_replay(
        run, kind="tool", name="case_update", input_fp=registry.fingerprint("case_update", arguments)
    )
    context = ToolContext.from_step(
        step, thread_id="life:self", source_ids=(run["request"]["source_message_id"],), case_ids=(case["id"],)
    )
    result = registry.execute("case_update", arguments, context)
    journal.complete(step, result.model_dump())
    changed = repo.get("alice", "case", case["id"])
    assert changed["status"] == status and changed["revision"] == case["revision"] + 1
    assert result.ok and result.receipt == {
        "write_status": "saved",
        "kind": "case",
        "id": case["id"],
        "revision": changed["revision"],
    }
    terminal = repo.fail_run(
        "alice", run["id"], "真实事项写入组件已核验，未发布对话或冻结L5", run["lease_token"], status="cancelled"
    )
    assert terminal["status"] == "cancelled" and terminal["result"] is None
    return changed, original


@pytest.mark.parametrize("status", ["paused", "closed"])
def test_real_case_update_component_then_runtime_index_is_read_only(
    lifecycle_repo: PostgresRepository, status: str
) -> None:
    repo = lifecycle_repo
    case, original = legal_mutation_component(repo, status)
    set_runtime(repo, "v4")
    intake, thread = ingress(repo)
    run = repo.claim_run("alice", submit(intake, thread, "那件事的进展，只看事项标题与状态")["id"])
    port = ScriptedPort([answer("", [ToolCall("index", "case_list", {})]), answer("事项状态索引〔e1〕")])
    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        intake.service, "alice", run["id"], run["lease_token"]
    )
    assert result["text"] == "事项状态索引〔e1〕" and result["meta"]["case_ids"] == []
    tools = [message for message in port.requests[-1]["messages"] if message.role == "tool"]
    assert len(tools) == 1
    assert json.loads(tools[0].content)["data"]["cases"] == [
        {"id": case["id"], "title": case["title"], "status": status, "revision": case["revision"]}
    ]
    assert "goal" not in tools[0].content and original["content"] not in tools[0].content
    current = repo.fetch_run("alice", run["id"])
    assert current["request"].get("case_ids", []) == [] and "message:" + original["id"] not in current["state_version"]
    assert repo.get("alice", "case", case["id"])["revision"] == case["revision"]


@pytest.mark.parametrize("status", ["paused", "closed"])
def test_other_kinds_do_not_inherit_case_lifecycle_index_permission(
    lifecycle_repo: PostgresRepository, status: str
) -> None:
    prepared = prepared_history(lifecycle_repo)
    h, _, _, aliases, versions, _ = prepared
    note = lifecycle_repo.put("alice", "note", "synthetic-lifecycle-note", {"summary": "合成旧笔记", "status": status})
    aliases["e1"] = dict(aliases["e1"], kind="note", id=note["id"], revision=note["revision"])
    versions[entity_dependency("note", note["id"])] = note["revision"]
    lifecycle_repo.set_run_dependencies("alice", h.run["id"], versions, h.run["lease_token"])
    with pytest.raises(CoreError):
        finish(prepared)
    assert_unpublished(lifecycle_repo, h.run["id"])


def test_unknown_case_status_with_real_index_proof_is_still_rejected(lifecycle_repo: PostgresRepository) -> None:
    prepared = prepared_history(lifecycle_repo, status="unknown-synthetic-case-state")
    with pytest.raises(CoreError):
        finish(prepared)
    assert_unpublished(lifecycle_repo, prepared[0].run["id"])

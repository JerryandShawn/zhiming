"""Historical title/status indexes are evidence without selected-case write authority."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from mingjing_core.agent.loop_codec import extend_aliases, verified_versions
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository

from .test_case_index_lineage_pg import existing_case, index_step
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_thread_inbox_pg import ingress, set_runtime, submit
from .test_toolkit_pg import setup


@pytest.fixture(name="history_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def prepared_history(repo: PostgresRepository, *, status: str = "done") -> tuple[Any, ...]:
    case, source = existing_case(repo)
    case = repo.update("alice", "case", case["id"], {"status": status}, expected_revision=case["revision"])
    h = setup(repo, "那件事的进展，只看历史索引")
    step, result = index_step(h)
    h.journal.complete(step, result.model_dump())
    versions, records = verified_versions(h.service, h.run, "case_list", result)
    versions["message:" + h.source["id"]] = h.source["revision"]
    repo.set_run_dependencies("alice", h.run["id"], versions, h.run["lease_token"])
    aliases: dict[str, dict[str, Any]] = {}
    extend_aliases(aliases, records)
    return h, case, source, aliases, versions, repo.get_revision("alice")


@pytest.mark.parametrize("status", ["open", "done", "archived"])
def test_real_history_index_can_be_cited_without_disclosing_unselected_body(
    history_repo: PostgresRepository, status: str
) -> None:
    repo = history_repo
    case, original = existing_case(repo)
    if status != case["status"]:
        case = repo.update("alice", "case", case["id"], {"status": status}, expected_revision=case["revision"])
    set_runtime(repo, "v4")
    intake, thread = ingress(repo)
    run = repo.claim_run("alice", submit(intake, thread, "那件事的进展，只看看历史事项标题和状态")["id"])
    port = ScriptedPort([answer("", [ToolCall("index", "case_list", {})]), answer("历史事项索引〔e1〕")])
    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        intake.service, "alice", run["id"], run["lease_token"]
    )
    assert result["text"] == "历史事项索引〔e1〕" and result["meta"]["case_ids"] == []
    assert result["used_fact_ids"] == [] and result["used_claim_ids"] == []
    current = repo.fetch_run("alice", run["id"])
    assert current["status"] == "succeeded" and current["request"].get("case_ids", []) == []
    assert current["state_version"][entity_dependency("case", case["id"])] == case["revision"]
    tool_messages = [message for message in port.requests[1]["messages"] if message.role == "tool"]
    assert len(tool_messages) == 1
    projected = json.loads(tool_messages[0].content)["data"]
    assert projected["cases"] == [
        {"id": case["id"], "title": case["title"], "status": status, "revision": case["revision"]}
    ]
    assert original["content"] not in tool_messages[0].content and "goal" not in tool_messages[0].content
    assert "message:" + original["id"] not in current["state_version"]
    assert repo.get("alice", "case", case["id"])["revision"] == case["revision"]


@pytest.mark.parametrize("status", ["done", "archived"])
def test_reading_historical_index_does_not_grant_case_write_scope(
    history_repo: PostgresRepository, status: str
) -> None:
    repo = history_repo
    case, _ = existing_case(repo)
    case = repo.update("alice", "case", case["id"], {"status": status}, expected_revision=case["revision"])
    set_runtime(repo, "v4")
    intake, thread = ingress(repo)
    run = repo.claim_run("alice", submit(intake, thread, "那件事的进展，目标改成合成新计划")["id"])
    write = {
        "id": case["id"],
        "expected_revision": case["revision"],
        "message_id": run["request"]["source_message_id"],
        "quote": run["request"]["message"],
        "changes": {"goal": "合成新计划"},
    }
    port = ScriptedPort(
        [
            answer("", [ToolCall("index", "case_list", {})]),
            answer("", [ToolCall("not-selected", "case_update", write)]),
            answer("仅回顾历史索引〔e1〕"),
        ]
    )
    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        intake.service, "alice", run["id"], run["lease_token"]
    )
    assert result["text"] == "仅回顾历史索引〔e1〕" and result["meta"]["case_ids"] == []
    tool_messages = [message for message in port.requests[-1]["messages"] if message.role == "tool"]
    assert any("AUTH_SCOPE_ERROR" in message.content for message in tool_messages)
    assert repo.get("alice", "case", case["id"])["revision"] == case["revision"]


@pytest.mark.parametrize("status", ["done", "archived"])
def test_repeated_current_history_reads_keep_the_first_verified_alias(
    history_repo: PostgresRepository, status: str
) -> None:
    repo = history_repo
    case, _ = existing_case(repo)
    case = repo.update("alice", "case", case["id"], {"status": status}, expected_revision=case["revision"])
    set_runtime(repo, "v4")
    intake, thread = ingress(repo)
    run = repo.claim_run("alice", submit(intake, thread, "那件事的进展，只看看历史索引")["id"])
    port = ScriptedPort(
        [
            answer("", [ToolCall("index-first", "case_list", {}), ToolCall("index-second", "case_list", {})]),
            answer("同一条历史索引〔e1〕"),
        ]
    )
    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        intake.service, "alice", run["id"], run["lease_token"]
    )
    assert result["text"] == "同一条历史索引〔e1〕" and result["meta"]["case_ids"] == []
    tools = [json.loads(message.content)["data"] for message in port.requests[-1]["messages"] if message.role == "tool"]
    assert len(tools) == 2 and all(list(tool["registered_aliases"]) == ["e1"] for tool in tools)
    assert all(tool["registered_aliases"]["e1"]["id"] == case["id"] for tool in tools)

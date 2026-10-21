"""Legal CaseChanges generate lifecycle rows before a separate read-only index run."""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

from .test_case_index_lineage_pg import existing_case
from .test_loop_cycle_case_versions_pg import selected_run
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_thread_inbox_pg import ingress, set_runtime, submit


@pytest.fixture(name="lifecycle_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def legal_transition(repo: PostgresRepository, status: str) -> tuple[dict[str, Any], dict[str, Any]]:
    case, original = existing_case(repo)
    text = "请将合成事项暂停" if status == "paused" else "请将合成事项关闭"
    run = selected_run(repo, case["id"], text)
    arguments = {
        "id": case["id"],
        "expected_revision": case["revision"],
        "message_id": run["request"]["source_message_id"],
        "quote": text,
        "changes": {"status": status},
    }
    port = ScriptedPort(
        [answer("", [ToolCall("legal-status", "case_update", arguments)]), answer("事项状态操作已完成")]
    )
    envelope = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
    )
    changed = repo.get("alice", "case", case["id"])
    assert changed["status"] == status and changed["revision"] == case["revision"] + 1
    assert any(
        row.get("write_status") == "saved" and row.get("kind") == "case" and row.get("id") == case["id"]
        for row in envelope["receipts"]
    )
    return changed, original


@pytest.mark.parametrize("status", ["paused", "closed"])
def test_legally_updated_case_is_citable_by_a_later_read_only_index(
    lifecycle_repo: PostgresRepository, status: str
) -> None:
    repo = lifecycle_repo
    case, original = legal_transition(repo, status)
    prior = repo.get("alice", "thread", "life:self")["context_cache"]
    set_runtime(repo, "v4")
    intake, thread = ingress(repo)
    run = repo.claim_run("alice", submit(intake, thread, "那件事的进展，只看事项标题与当前状态")["id"])
    port = ScriptedPort([answer("", [ToolCall("index", "case_list", {})]), answer("这条事项索引〔e1〕")])
    envelope = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        intake.service, "alice", run["id"], run["lease_token"]
    )
    assert envelope["text"] == "这条事项索引〔e1〕" and envelope["meta"]["case_ids"] == []
    tools = [message for message in port.requests[-1]["messages"] if message.role == "tool"]
    assert len(tools) == 1
    assert json.loads(tools[0].content)["data"]["cases"] == [
        {"id": case["id"], "title": case["title"], "status": status, "revision": case["revision"]}
    ]
    assert "goal" not in tools[0].content and original["content"] not in tools[0].content
    assert repo.fetch_run("alice", run["id"])["request"].get("case_ids", []) == []
    assert repo.get("alice", "case", case["id"])["revision"] == case["revision"]
    cache = repo.get("alice", "thread", "life:self")["context_cache"]
    assert cache["epoch"] == prior["epoch"] + 1
    assert cache["visibility_sha256"] == fingerprint({"case_ids": []}) != prior["visibility_sha256"]
    assert all(
        original["content"] not in str(message.content) for request in port.requests for message in request["messages"]
    )

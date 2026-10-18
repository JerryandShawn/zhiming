"""Regression: selected cases with real feedback must admit exact context dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.journal import Journal
from mingjing_core.agent.loop_codec import verified_versions
from mingjing_core.agent.toolkit import ToolContext, ToolRegistry, ToolResult
from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import ScriptedPort, answer, cycle, modify
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="cycle_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def selected_run(repo: PostgresRepository, case_id: str, text: str) -> dict[str, Any]:
    source = MemoryService(repo).receive(
        "alice", content=text, source_id=uuid.uuid4().hex, at=get_clock().now(), case_ids=[case_id]
    )
    run = repo.queue_run(
        "alice",
        uuid.uuid4().hex,
        {"message": text, "source_message_id": source["id"], "case_ids": [case_id]},
        case_ids=[case_id],
    )
    modify(repo, run, "runtime='v4',thread_id='life:self'")
    return repo.claim_run("alice", run["id"], lease_seconds=3600)


def existing_case_with_feedback(repo: PostgresRepository) -> tuple[dict[str, Any], ToolRegistry]:
    case = MemoryService(repo).create_case("alice", "self", "合成事项")
    registry = ToolRegistry(AgentToolsService(repo))
    for index in range(2):
        run = selected_run(repo, case["id"], f"我完成合成步骤{index}")
        versions = {"message:" + run["request"]["source_message_id"]: 1}
        repo.set_run_dependencies("alice", run["id"], versions, run["lease_token"])
        args = {
            "id": case["id"],
            "kind": "progress",
            "content": run["request"]["message"],
            "message_id": run["request"]["source_message_id"],
            "expected_revision": case["revision"],
        }
        journal = Journal(repo, "alice")
        step = journal.next_or_replay(
            run,
            kind="tool",
            name="case_add_event",
            input_fp=registry.fingerprint("case_add_event", args, source_versions=versions),
        )
        ctx = ToolContext.from_step(
            step,
            thread_id="life:self",
            source_ids=(run["request"]["source_message_id"],),
            case_ids=(case["id"],),
            source_versions=versions,
        )
        result = registry.execute("case_add_event", args, ctx)
        assert result.ok and result.receipt["kind"] == "feedback"
        journal.complete(step, result.model_dump())
    assert len(repo.list("alice", "feedback")) == 2
    return case, registry


def test_case_with_two_real_feedback_events_can_freeze_context_and_run_loop(cycle_repo: PostgresRepository) -> None:
    repo = cycle_repo
    case, registry = existing_case_with_feedback(repo)
    run = selected_run(repo, case["id"], "请回顾合成事项")
    engine = ContextEngine(MemoryService(repo), "合成系统")
    built = engine.build("alice", run["request"]["source_message_id"], case_ids=(case["id"],))
    assert len([key for key in built.injected_versions if key.startswith("entity:feedback:")]) == 2
    frozen = AgentSnapshotStore(repo).load_or_build(run, lambda: built)
    result = cycle(ScriptedPort([answer("合成回顾")]), registry, run, frozen).execute()
    assert result.stop_reason == "completed" and result.text == "合成回顾"


def test_case_lineage_registration_uses_repository_dependency_semantics(cycle_repo: PostgresRepository) -> None:
    repo = cycle_repo
    case, registry = existing_case_with_feedback(repo)
    run = selected_run(repo, case["id"], "回顾合成事项")
    with repo.transaction("alice") as connection:
        actual = repo._version(connection, "alice", "case:" + case["id"])
        exact = repo._version(connection, "alice", entity_dependency("case", case["id"]))
    assert actual == 3 and exact == case["revision"] == 1
    result = ToolResult(
        ok=True, receipt={"kind": "case", "id": case["id"], "revision": case["revision"]}, summary="合成回执"
    )
    versions, _ = verified_versions(registry.service, run, "case_update", result)
    assert repo.verify_versions("alice", versions)

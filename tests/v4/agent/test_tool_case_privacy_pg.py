"""Required source erasure behavior for tool-authored case projections."""

from __future__ import annotations

import pytest

from mingjing_core.agent.journal import Journal
from mingjing_core.agent.toolkit import ToolContext
from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import PostgresRepository

from .test_tool_interactions_pg import call, case
from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as source_tool_repo


@pytest.fixture
def tool_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_tool_repo.__wrapped__(p2_repo, monkeypatch)


def withdrawn_case(repo: PostgresRepository) -> tuple[str, str]:
    h = setup(repo, "请记住我已完成合成报告")
    ca = case(h)
    fact = MemoryService(repo).save_fact(
        "alice",
        "self",
        h.source["id"],
        h.source["content"],
        "background",
        case_id=ca["id"],
    )
    call(
        h,
        "case_update",
        {
            "id": ca["id"],
            "changes": {"goal": "完成合成报告"},
            "expected_revision": ca["revision"],
            "message_id": h.source["id"],
            "quote": h.source["content"],
        },
    )
    updated = repo.get("alice", "case", ca["id"])
    event, _ = call(
        h,
        "case_add_event",
        {
            "id": ca["id"],
            "kind": "completed",
            "content": h.source["content"],
            "message_id": h.source["id"],
            "expected_revision": updated["revision"],
        },
    )
    h.finish()
    deletion = setup(repo, "请忘记刚才的合成记录")
    case(deletion)
    args = {"fact_id": fact["id"], "message_id": deletion.source["id"]}
    step = Journal(repo, "alice").next_or_replay(
        deletion.run,
        kind="tool",
        name="memory_forget",
        input_fp=deletion.registry.fingerprint("memory_forget", args),
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(deletion.source["id"],), case_ids=(ca["id"],))
    result = deletion.registry.execute("memory_forget", args, ctx)
    assert result.ok and result.receipt["write_status"] == "deleted"
    return ca["id"], event.receipt["id"]


def test_withdrawing_source_erases_case_event_body(tool_repo: PostgresRepository) -> None:
    _, event = withdrawn_case(tool_repo)
    row = tool_repo.get("alice", "feedback", event, include_deleted=True)
    assert row["status"] == "deleted" and not row.get("content")


def test_withdrawing_source_erases_projected_goal_but_preserves_case_identity(tool_repo: PostgresRepository) -> None:
    ident, _ = withdrawn_case(tool_repo)
    row = tool_repo.get("alice", "case", ident)
    assert row["state"].get("goal") == ""
    assert row["title"] == "合成事项"

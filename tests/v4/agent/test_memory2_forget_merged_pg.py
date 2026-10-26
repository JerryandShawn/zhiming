"""F05: forget actual merged writes, plus explicitly selected historical values."""

from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.agent_tools_policy import V4FactMemory

from .test_memory2_slots_pg import pair, slots_repo, update
from .test_toolkit_pg import setup


@pytest.fixture(name="tool_repo")
def erasure_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return slots_repo.__wrapped__(p2_repo, monkeypatch)


def test_f05_real_merged_writes_are_all_erased_and_revoked(tool_repo):
    retained = None
    for _ in range(3):
        h = setup(tool_repo, "我喜欢合成晨跑")
        result, _, _ = h.write("preference")
        assert result.ok
        retained = result.receipt["fact_id"]
        h.finish()
    original = tool_repo.list("alice", "fact", include_deleted=True)
    assert len(original) == 3 and sum(row["status"] == "merged" for row in original) == 2
    h = setup(tool_repo, "把我合成晨跑的事忘了")
    deleted, ctx = h.call("memory_forget", {"fact_id": retained, "message_id": h.source["id"]})
    assert deleted.ok and set(deleted.receipt["affected_ids"]) == {row["id"] for row in original}
    with tool_repo.transaction("alice") as connection:
        rows = connection.execute(
            sql.SQL("SELECT id,status,data FROM {} WHERE owner=%s AND kind='fact'").format(
                tool_repo.table("core_entities")
            ),
            ("alice",),
        ).fetchall()
    assert len(rows) == 3 and all(row["status"] == "deleted" and row["data"] == {} for row in rows)
    assert all(tool_repo.is_revoked("alice", "fact", row["id"]) for row in original)
    assert h.registry.execute("memory_forget", {"fact_id": retained, "message_id": h.source["id"]}, ctx) == deleted
    h.finish()


def test_recursive_merged_aliases_are_erased_without_cross_subject_traversal(tool_repo):
    old, _ = pair(tool_repo)
    base = {
        key: value for key, value in old.items() if key not in {"id", "revision", "created_at", "updated_at", "owner"}
    }
    for ident, target in (("alias1", old["id"]), ("alias2", "alias1")):
        tool_repo.put("alice", "fact", ident, dict(base, status="merged", merged_into=target), expected_revision=0)
    result = V4FactMemory(tool_repo).retire_fact("alice", old["id"], expected_revision=old["revision"])
    assert set(result["affected_fact_ids"]) == {old["id"], "alias1", "alias2"}
    assert all(tool_repo.is_revoked("alice", "fact", ident) for ident in result["affected_fact_ids"])


def test_historical_original_can_be_forgotten_through_the_real_tool(tool_repo):
    old, new = pair(tool_repo)
    update(tool_repo, old, new)
    h = setup(tool_repo, "把我杭州的记录忘记")
    deleted, _ = h.call("memory_forget", {"fact_id": old["id"], "message_id": h.source["id"]})
    assert deleted.ok and deleted.receipt["write_status"] == "deleted"
    assert tool_repo.get("alice", "fact", old["id"], include_deleted=True)["status"] == "deleted"
    current = tool_repo.get("alice", "fact", new["id"])
    assert current["supersedes"] is None and current["valid_to"] is None
    assert [row["id"] for row in h.service.memory.facts("alice")] == [new["id"]]
    h.finish()

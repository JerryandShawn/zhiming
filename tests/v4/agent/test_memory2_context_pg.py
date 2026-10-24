"""Real L4 snapshots retrieve facts using original-time importance, after source checks."""

from mingjing_core.application.memory import MemoryService

from .test_context_pg import context_memory_fixture as context_memory_fixture
from .test_context_pg import receive
from .test_context_time_retrieval_pg import l4


def test_fact_ranking_enters_non_temporal_l4_without_losing_dependency_versions(memory: MemoryService) -> None:
    old = receive(memory, "请记住我喜欢合成徒步", "old", at="2026-04-20T10:30:00+08:00")
    old_fact = memory.save_fact("alice", "self", old["id"], "我喜欢合成徒步")
    new = receive(memory, "请记住我喜欢合成徒步", "new", at="2026-10-17T10:30:00+08:00")
    new_fact = memory.save_fact("alice", "self", new["id"], "我喜欢合成徒步")
    context, values = l4(memory, receive(memory, "合成徒步", "query"))
    facts = [value for value in values if value["kind"] == "fact"]
    assert [context.alias_map[value["alias"]]["id"] for value in facts] == [new_fact["id"], old_fact["id"]]
    assert context.read_counts["search_candidates"] <= 100
    for row in (old, new):
        assert context.injected_versions["message:" + row["id"]] == row["revision"]


def test_withdrawn_fact_never_reenters_l4_through_its_rank(memory: MemoryService) -> None:
    old = receive(memory, "请记住我喜欢合成登山", "withdrawn")
    fact = memory.save_fact("alice", "self", old["id"], "我喜欢合成登山")
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    context, values = l4(memory, receive(memory, "合成登山", "query"))
    assert all(row["id"] != fact["id"] for row in context.alias_map.values())
    assert all(value["kind"] != "fact" for value in values)

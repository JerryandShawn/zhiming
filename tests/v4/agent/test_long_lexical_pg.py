"""181k-character originals round-trip through actual PG without text truncation."""

import time

import pytest

from mingjing_core.application.memory import MemoryService
from mingjing_core.memory.tokenize import tokenize


@pytest.mark.parametrize("pattern", ["x", "龘靐齉爩", "日主喜用神夜班考研"])
def test_181k_original_is_preserved_and_terms_remain_retrievable(p2_repo, pattern, record_property):
    content = (pattern * (181000 // len(pattern) + 1))[:181000]
    started = time.perf_counter()
    memory = MemoryService(p2_repo)
    source = memory.receive("alice", content=content, source_id="long-lexical-original")
    assert memory.get_source("alice", source["id"])["content"] == content
    assert p2_repo.get("alice", "message", source["id"])["content"] == content
    tokens = tokenize(pattern if pattern != "x" else "x" * 512)
    matches = p2_repo.search("alice", "self", tokens, ["message"])
    assert source["id"] in {row["id"] for row in matches}
    same = memory.receive("alice", content=content, source_id="long-lexical-original")
    assert same["id"] == source["id"] and len(p2_repo.list("alice", "message")) == 1
    assert MemoryService(p2_repo).snapshot("alice")["facts"] == []
    record_property("input_characters", 181000)
    record_property("round_trip_seconds", round(time.perf_counter() - started, 6))

"""Memory2 ranking is exercised through real journal, tool and isolated PG services."""

from datetime import timedelta

import pytest

from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock

from .test_toolkit_pg import SAID_AT, setup
from .test_toolkit_pg import tool_repo as base_tool_repo


@pytest.fixture(name="tool_repo")
def ranking_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def saved(repo, text, ident, *, days=0, kind="preference"):
    memory = MemoryService(repo)
    source = memory.receive(
        "alice",
        content="请记住" + text,
        source_id=ident,
        at=SAID_AT - timedelta(days=days),
        channel="synthetic",
    )
    fact = memory.save_fact("alice", "self", source["id"], text, kind)
    assert fact["write_status"] == "saved"
    return fact, source


def test_real_search_prefers_recent_preference_at_equal_lexical_relevance(tool_repo):
    old, _ = saved(tool_repo, "我喜欢合成散步", "old", days=180)
    new, _ = saved(tool_repo, "我喜欢合成散步", "new")
    h = setup(tool_repo, "检索合成散步")
    result, _ = h.call("memory_search", {"query": "合成散步", "kinds": ["fact"]})
    assert result.ok and result.data["vector_available"] is False
    assert [item["id"] for item in result.data["items"]] == [new["id"], old["id"]]
    assert [item["memory_importance"] for item in result.data["items"]] == [0.6, 0.3]


def test_old_constraint_keeps_importance_and_revocation_removes_it(tool_repo):
    fact, source = saved(tool_repo, "我不能上合成夜班", "constraint", days=720, kind="constraint")
    h = setup(tool_repo, "检索合成夜班")
    result, _ = h.call("memory_search", {"query": "合成夜班", "kinds": ["fact"]})
    assert result.ok and result.data["items"][0]["memory_importance"] == 0.9
    MemoryService(tool_repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    result, _ = h.call("memory_search", {"query": "合成夜班", "kinds": ["fact"]})
    assert result.ok and result.data["items"] == []
    assert tool_repo.get("alice", "message", source["id"])["status"] == "active"


def test_future_host_clock_does_not_replace_injected_tool_clock(tool_repo):
    fact, _ = saved(tool_repo, "我喜欢合成读书", "read", days=180)
    h = setup(tool_repo, "检索合成读书")
    h.service.clock = FrozenClock(SAID_AT + timedelta(days=180))
    result, _ = h.call("memory_search", {"query": "合成读书", "kinds": ["fact"]})
    assert result.ok and result.data["items"][0]["id"] == fact["id"]
    assert result.data["items"][0]["memory_importance"] == 0.15


def test_stale_high_importance_source_is_excluded_before_ranking(tool_repo):
    fact, source = saved(tool_repo, "我喜欢合成漫步", "stale")
    tool_repo.update(
        "alice",
        "fact",
        fact["id"],
        {"importance": 1.0},
        expected_revision=fact["revision"],
    )
    tool_repo.update(
        "alice",
        "message",
        source["id"],
        {"synthetic_revision": True},
        expected_revision=1,
    )
    h = setup(tool_repo, "检索合成漫步")
    result, _ = h.call("memory_search", {"query": "合成漫步", "kinds": ["fact"]})
    assert result.ok and result.data["items"] == []

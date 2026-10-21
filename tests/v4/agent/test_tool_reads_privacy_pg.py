"""Tool retrieval cannot widen case scope or leak invalid profile/source fields."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from mingjing_core.agent.toolkit import ToolContext
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_toolkit_pg import SAID_AT, setup
from .test_toolkit_pg import tool_repo as tool_repo_fixture


@pytest.fixture(name="tool_repo")
def privacy_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return tool_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def search(h, query: str, kinds: list[str]):
    result, _ = h.call("memory_search", {"query": query, "kinds": kinds})
    assert result.ok
    return result.data["items"]


def test_unselected_case_original_and_note_are_absent(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "当前普通问题")
    memory = MemoryService(tool_repo)
    case = memory.create_case("alice", "self", "不选择的事项")
    source = memory.receive("alice", content="秘密考研安排", source_id="hidden", at=SAID_AT, case_ids=[case["id"]])
    tool_repo.put(
        "alice", "note", "note-hidden", {"summary": "秘密考研推测", "source_ids": [source["id"]]}, expected_revision=0
    )
    assert search(h, "秘密", ["message", "note"]) == []


def test_incognito_and_wrong_subject_source_ids_cannot_authorize_derived_note(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "当前普通问题")
    memory = MemoryService(tool_repo)
    source = memory.receive("alice", content="秘密无痕内容", source_id="private", at=SAID_AT)
    tool_repo.update("alice", "message", source["id"], {"thread_id": "incognito:test"}, expected_revision=1)
    tool_repo.put(
        "alice", "note", "note-private", {"summary": "秘密推测", "source_ids": [source["id"]]}, expected_revision=0
    )
    tool_repo.create_subject("alice", "other", "合成人物")
    other = memory.receive("alice", "other", content="秘密他人内容", source_id="other", at=SAID_AT)
    tool_repo.put(
        "alice", "episode", "episode-other", {"summary": "秘密情景", "source_ids": [other["id"]]}, expected_revision=0
    )
    assert search(h, "秘密", ["message", "note", "episode"]) == []


def test_partial_message_projection_never_returns_raw_search_tokens(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "当前普通问题")
    memory = MemoryService(tool_repo)
    source = memory.receive("alice", content="考研安排。秘密代号", source_id="withdraw", at=SAID_AT)
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(
            connection,
            "alice",
            "source_span",
            "withdrawn-code",
            "deleted",
            {"message_id": source["id"], "start": 5, "end": len(source["content"])},
        )
    items = search(h, "考研", ["message"])
    assert len(items) == 1
    assert "秘密代号" not in json.dumps(items, ensure_ascii=False)
    assert "search_tokens" not in items[0] and "[该资料已撤销]" in items[0]["content"]


def test_note_source_ids_without_refs_still_follow_withdrawals(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "当前普通问题")
    source = MemoryService(tool_repo).receive("alice", content="考研秘密", source_id="withdraw", at=SAID_AT)
    tool_repo.put(
        "alice", "note", "note-source-only", {"summary": "考研推测", "source_ids": [source["id"]]}, expected_revision=0
    )
    assert len(search(h, "考研", ["note"])) == 1
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(
            connection,
            "alice",
            "source_span",
            "withdrawn-source",
            "deleted",
            {"message_id": source["id"], "start": 0, "end": 2},
        )
    assert search(h, "考研", ["note"]) == []


def test_stale_profile_fact_cannot_survive_via_profile_map(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "请记住我的名字是合成甲")
    fact = MemoryService(tool_repo).save_fact(
        "alice", "self", h.source["id"], h.source["content"], "profile", field="name", value="合成甲"
    )
    assert fact["write_status"] == "saved"
    tool_repo.update("alice", "message", h.source["id"], {"test_revision": True}, expected_revision=1)
    result, _ = h.call("profile_get", {})
    assert result.ok and result.data["profile"] == {} and result.data["facts"] == []


def test_context_cannot_expand_persisted_selected_cases(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "当前普通问题")
    memory = MemoryService(tool_repo)
    case = memory.create_case("alice", "self", "本轮未选择事项")
    memory.receive("alice", content="秘密考研安排", source_id="hidden", at=SAID_AT, case_ids=[case["id"]])
    for name, args in (
        ("memory_search", {"query": "秘密", "kinds": ["message"]}),
        ("profile_get", {}),
        ("calendar_lookup", {"start_date": "2026-10-17"}),
    ):
        _, ctx = h.call(name, args)
        result = h.registry.execute(name, args, replace(ctx, case_ids=(case["id"],)))
        assert not result.ok and "秘密" not in str(result.data)


def test_first_effect_cannot_use_arguments_different_from_durable_fingerprint(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我喜欢夜班")
    args = {"message_id": h.source["id"], "quote": h.source["content"], "summary": "原摘要", "kind": "preference"}
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="memory_write", input_fp=h.registry.fingerprint("memory_write", args)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    before = tool_repo.get_revision("alice")
    changed = dict(args, summary="被替换摘要")
    assert h.registry.execute("memory_write", changed, ctx).data["code"] == "tool_arguments_mismatch"
    with pytest.raises(EvidenceError):
        h.service.execute("memory_write", changed, ctx)
    assert tool_repo.get_revision("alice") == before and not tool_repo.list("alice", "fact")
    assert h.registry.execute("memory_write", args, ctx).ok


def test_equivalent_default_arguments_have_the_same_canonical_fingerprint(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "当前问题")
    _, ctx = h.call("time_context", {})
    assert h.registry.fingerprint("time_context", {}) == h.registry.fingerprint(
        "time_context", {"date": None, "time": None}
    )
    assert h.registry.execute("time_context", {"date": None, "time": None}, ctx).ok

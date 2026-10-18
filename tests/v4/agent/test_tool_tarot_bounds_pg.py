"""U7 bounded-history and revocation boundaries execute real PostgreSQL services."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pytest

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.agent.toolkit import ToolContext
from mingjing_core.agent.tools.tarot_parameters import TarotRead
from mingjing_core.application.agent_tools_contracts import tool_input_fingerprint
from mingjing_core.application.agent_tools_tarot import execute_tarot
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock

from .test_tool_tarot_pg import QUESTION, call, harness, select_request
from .test_tool_tarot_pg import tarot_env as source_tarot_env


@pytest.fixture
def tarot_env(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PostgresRepository, FrozenClock]:
    return source_tarot_env.__wrapped__(p2_repo, monkeypatch)


def seed_history(repo: PostgresRepository, count: int) -> None:
    ca = MemoryService(repo).create_case("alice", "self", "合成历史事项", operation_id="history-case")
    tarot = TarotService(repo)
    for index in range(count):
        tarot.create_draw(
            "alice",
            subject_id="self",
            case_id=ca["id"],
            question=f"历史候选问题编号{index}",
            spread_id="focus1",
            draw_source="auto",
            stage=f"history-{index}",
            idempotency_key=f"history-{index}",
        )


def test_two_hundred_recent_candidates_fail_closed_but_old_history_does_not_block(
    tarot_env: tuple[PostgresRepository, FrozenClock],
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    from datetime import timedelta

    repo, clock = tarot_env
    seed_history(repo, 201)
    reads: list[str] = []
    original = TarotService.get

    def measured_get(service: TarotService, owner: str, ident: str) -> dict[str, Any]:
        reads.append(ident)
        return original(service, owner, ident)

    monkeypatch.setattr(TarotService, "get", measured_get)
    h = harness(tarot_env)
    before = repo.get_revision("alice")
    started = time.monotonic()
    result, _, _ = call(h)
    record_property("recent_guard_elapsed_ms", round((time.monotonic() - started) * 1000, 3))
    assert not result.ok and result.receipt["code"] == "recent_draw_check_limit"
    assert len(reads) == 200 and repo.get_revision("alice") == before
    clock.advance(timedelta(hours=25))
    reads.clear()
    h = harness(tarot_env)
    result, _, _ = call(h)
    assert result.ok and len(reads) == 1
    assert len(TarotService(repo).list_draws("alice", limit=200)) == 200


def test_real_foreign_owner_selected_draw_never_becomes_readable(
    tarot_env: tuple[PostgresRepository, FrozenClock],
) -> None:
    repo, _ = tarot_env
    ca = MemoryService(repo).create_case("bob", "self", "合成另一用户事项", operation_id="bob-case")
    tarot = TarotService(repo)
    draw = tarot.create_draw(
        "bob",
        subject_id="self",
        case_id=ca["id"],
        question=QUESTION,
        draw_source="auto",
        idempotency_key="bob-draw",
    )["draw"]
    tarot.reveal("bob", draw["id"])
    h = harness(tarot_env)
    select_request(h, draw["id"])
    values = TarotRead(draw_id=draw["id"]).model_dump()
    step = h.journal.next_or_replay(
        h.run,
        kind="tool",
        name="tarot_read",
        input_fp=tool_input_fingerprint("tarot_read", values),
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    before = repo.get_revision("alice")
    with pytest.raises(ScopeError):
        execute_tarot(h.service, "tarot_read", values, ctx)
    assert repo.get_revision("alice") == before and tarot.list_draws("alice") == []


def test_unrelated_withdrawn_span_keeps_original_question_and_fixed_cards(
    tarot_env: tuple[PostgresRepository, FrozenClock],
) -> None:
    repo, _ = tarot_env
    h = harness(tarot_env, QUESTION + "。我喜欢夜班")
    fact = MemoryService(repo).save_fact("alice", "self", h.source["id"], "我喜欢夜班", "preference")
    assert fact["write_status"] == "saved"
    result, _, _ = call(h, args={"question": QUESTION, "message_id": h.source["id"], "draw_source": "auto"})
    ident = result.receipt["draw_id"]
    fixed = TarotService(repo).reveal("alice", ident)["cards"]
    MemoryService(repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    current = harness(tarot_env, "请沿用已揭示的牌")
    select_request(current, ident)
    read, _, _ = call(current, "tarot_read", {"draw_id": ident})
    assert read.ok and read.data["draw"]["cards"] == fixed
    assert "我喜欢夜班" not in str(read.data)


def test_message_revocation_ledger_blocks_still_active_question_row(
    tarot_env: tuple[PostgresRepository, FrozenClock],
) -> None:
    repo, _ = tarot_env
    h = harness(tarot_env)
    result, _, _ = call(h, args={"question": QUESTION, "message_id": h.source["id"], "draw_source": "auto"})
    ident = result.receipt["draw_id"]
    TarotService(repo).reveal("alice", ident)
    select_request(h, ident)
    with repo.transaction("alice") as connection:
        repo.revoke(connection, "alice", "message", h.source["id"], "stopped")
    assert repo.get("alice", "message", h.source["id"])["status"] == "active"
    with pytest.raises(EvidenceError):
        call(h, "tarot_read", {"draw_id": ident})

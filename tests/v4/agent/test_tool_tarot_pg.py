"""U7 wraps the real fixed-deck service in the same owner transaction."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.agent.toolkit import ToolContext, ToolResult
from mingjing_core.agent.tools.tarot_parameters import TarotRead, TarotStart
from mingjing_core.application.agent_tools_contracts import tool_input_fingerprint
from mingjing_core.application.agent_tools_tarot import execute_tarot
from mingjing_core.application.agent_tools_tarot_guard import tarot_mode
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock

from .test_toolkit_pg import SAID_AT, Harness, setup
from .test_toolkit_pg import tool_repo as source_tool_repo

QUESTION = "这次合成面试会顺利通过吗"


@pytest.fixture
def tarot_env(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PostgresRepository, FrozenClock]:
    repo = source_tool_repo.__wrapped__(p2_repo, monkeypatch)
    clock = FrozenClock(SAID_AT)
    monkeypatch.setattr("mingjing_core.adapters.tarot.get_clock", lambda: clock)
    return repo, clock


def harness(env: tuple[PostgresRepository, FrozenClock], text: str = QUESTION) -> Harness:
    h = setup(env[0], text)
    h.service.clock = env[1]
    return h


def call(
    h: Harness,
    name: str = "tarot_start",
    args: dict[str, Any] | None = None,
    **flags: Any,
) -> tuple[ToolResult, ToolContext, dict[str, Any]]:
    raw = args or {"question": QUESTION, "message_id": h.source["id"]}
    values = (TarotStart if name == "tarot_start" else TarotRead).model_validate(raw).model_dump()
    step = h.journal.next_or_replay(h.run, kind="tool", name=name, input_fp=tool_input_fingerprint(name, values))
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],), **flags)
    return execute_tarot(h.service, name, values, ctx), ctx, values


def select_request(h: Harness, ident: str) -> None:
    with h.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET request=jsonb_set(request,'{{draw_id}}',%s) WHERE id=%s").format(
                h.repo.table("core_runs")
            ),
            (Jsonb(ident), h.run["id"]),
        )
    h.run = h.repo.fetch_run("alice", h.run["id"])


def test_pick_draw_hidden_cards_replay_and_user_reveal_then_fixed_read(
    tarot_env: tuple[PostgresRepository, FrozenClock],
) -> None:
    h = harness(tarot_env)
    result, ctx, args = call(h)
    draw = result.data["draw"]
    assert result.ok and len(draw["backs"]) == 78 and draw["cards"] == []
    revision = h.repo.get_revision("alice")
    replay = execute_tarot(h.service, "tarot_start", args, ctx)
    assert replay.data["draw"] == draw and h.repo.get_revision("alice") == revision
    tarot = TarotService(h.repo)
    for index, back in enumerate(draw["backs"][:3]):
        tarot.select("alice", draw["id"], back["back_id"], "synthetic-pick-" + str(index))
    selected = tarot.get("alice", draw["id"])
    assert all("card_id" not in item and not item["revealed"] for item in selected["cards"])
    tarot.reveal("alice", draw["id"])
    select_request(h, draw["id"])
    assert tarot_mode(h.service, ctx) == "tarot_read"
    read, _, _ = call(h, "tarot_read", {"draw_id": draw["id"]})
    assert read.ok and read.data["draw"]["cards"] == tarot.get_for_reading("alice", draw["id"])["cards"]


def test_twenty_four_hour_window_and_punctuation_do_not_create_new_decks(
    tarot_env: tuple[PostgresRepository, FrozenClock],
) -> None:
    repo, clock = tarot_env
    first = harness(tarot_env)
    draw, _, _ = call(first)
    clock.advance(timedelta(hours=23, minutes=59))
    second = harness(tarot_env, QUESTION + "？")
    before = repo.get_revision("alice")
    repeated, _, _ = call(second, args={"question": QUESTION + "？", "message_id": second.source["id"]})
    assert not repeated.ok and repeated.data["code"] == "recent_draw_exists"
    assert repeated.data["draw_id"] == draw.data["draw"]["id"] and repo.get_revision("alice") == before
    clock.advance(timedelta(minutes=1))
    third = harness(tarot_env)
    renewed, _, _ = call(third)
    assert renewed.ok and renewed.data["draw"]["id"] != draw.data["draw"]["id"]
    assert len(TarotService(repo).list_draws("alice")) == 2


@pytest.mark.parametrize(
    "statement,allowed",
    [
        ("我坚持重新抽牌", True),
        ("朋友说“请重新抽牌”", False),
        ("我不想重抽", False),
    ],
)
def test_model_flag_needs_current_user_insistence_and_never_changes_old_cards(
    tarot_env: tuple[PostgresRepository, FrozenClock],
    statement: str,
    allowed: bool,
) -> None:
    first = harness(tarot_env)
    result, _, _ = call(first, args={"question": QUESTION, "message_id": first.source["id"], "draw_source": "auto"})
    old = TarotService(first.repo).get("alice", result.receipt["draw_id"])
    second = harness(tarot_env, QUESTION + "。" + statement)
    result, _, _ = call(second, args={"question": QUESTION, "message_id": second.source["id"], "explicit_new": True})
    assert result.ok is allowed
    if not allowed:
        assert result.receipt["code"] == "explicit_redraw_required"
    assert TarotService(first.repo).get("alice", old["id"]) == old
    assert len(TarotService(first.repo).list_draws("alice")) == (2 if allowed else 1)


def test_cancelled_draw_does_not_bypass_same_question_guard(tarot_env: tuple[PostgresRepository, FrozenClock]) -> None:
    first = harness(tarot_env)
    result, _, _ = call(first)
    TarotService(first.repo).cancel("alice", result.receipt["draw_id"])
    second = harness(tarot_env)
    result, _, _ = call(second)
    assert not result.ok and result.receipt["code"] == "recent_draw_exists"


def test_two_simultaneous_runs_only_shuffle_one_deck(tarot_env: tuple[PostgresRepository, FrozenClock]) -> None:
    first, second = harness(tarot_env), harness(tarot_env)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(call, (first, second)))
    assert sorted(result[0].ok for result in results) == [False, True]
    assert len(TarotService(first.repo).list_draws("alice")) == 1


def test_selected_draw_identity_source_and_lease_are_authoritative(
    tarot_env: tuple[PostgresRepository, FrozenClock],
) -> None:
    h = harness(tarot_env)
    result, ctx, args = call(h, args={"question": QUESTION, "message_id": h.source["id"], "draw_source": "auto"})
    ident = result.receipt["draw_id"]
    with pytest.raises(LeaseConflict):
        execute_tarot(h.service, "tarot_start", args, replace(ctx, lease_token="wrong"))
    private, _, _ = call(h, args={"question": QUESTION, "message_id": h.source["id"]}, incognito=True)
    assert not private.ok and private.data["code"] == "incognito"
    TarotService(h.repo).reveal("alice", ident)
    select_request(h, ident)
    with pytest.raises(ScopeError):
        call(h, "tarot_read", {"draw_id": "other"})
    with h.repo.transaction("alice") as connection:
        h.repo.revoke(
            connection,
            "alice",
            "source_span",
            "withdrawn-question",
            "stopped",
            {"message_id": h.source["id"], "start": 0, "end": len(QUESTION)},
        )
    with pytest.raises(EvidenceError):
        call(h, "tarot_read", {"draw_id": ident})


def test_draw_mode_cannot_be_spoofed_by_unowned_request_or_model_flags(
    tarot_env: tuple[PostgresRepository, FrozenClock],
) -> None:
    h = harness(tarot_env)
    result, ctx, _ = call(h, args={"question": QUESTION, "message_id": h.source["id"], "draw_source": "auto"})
    ident = result.receipt["draw_id"]
    TarotService(h.repo).reveal("alice", ident)
    select_request(h, ident)
    assert tarot_mode(h.service, ctx) == "tarot_read"
    with pytest.raises(EvidenceError):
        call(h)
    select_request(h, "missing-or-foreign-draw")
    with pytest.raises(ScopeError):
        tarot_mode(h.service, ctx)


def test_draw_question_source_version_change_blocks_read(tarot_env: tuple[PostgresRepository, FrozenClock]) -> None:
    h = harness(tarot_env)
    result, _, _ = call(h, args={"question": QUESTION, "message_id": h.source["id"], "draw_source": "auto"})
    ident = result.receipt["draw_id"]
    TarotService(h.repo).reveal("alice", ident)
    select_request(h, ident)
    h.repo.update(
        "alice", "message", h.source["id"], {"synthetic_revision_change": True}, expected_revision=h.source["revision"]
    )
    with pytest.raises(EvidenceError):
        call(h, "tarot_read", {"draw_id": ident})


def test_registry_exposes_topic_and_persisted_draw_but_application_preserves_fixed_deck(
    tarot_env: tuple[PostgresRepository, FrozenClock],
) -> None:
    h = harness(tarot_env, "请用塔罗抽牌看看，" + QUESTION)
    raw = {"question": QUESTION, "message_id": h.source["id"], "draw_source": "auto"}
    values = TarotStart.model_validate(raw).model_dump()
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="tarot_start", input_fp=h.registry.fingerprint("tarot_start", raw)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    names = [spec.name for spec in h.registry.specs(ctx)]
    assert len(names) <= 15 and "tarot_start" in names and "tarot_read" not in names
    result = h.registry.execute("tarot_start", values, ctx)
    assert result.ok
    ident = result.receipt["draw_id"]
    TarotService(h.repo).reveal("alice", ident)
    select_request(h, ident)
    names = [spec.name for spec in h.registry.specs(ctx)]
    assert len(names) <= 15 and "tarot_read" in names and "tarot_start" in names
    unavailable = h.registry.execute("tarot_start", values, ctx)
    assert not unavailable.ok and unavailable.data["code"] == "REFERENCE_ERROR"
    raw_read = {"draw_id": ident}
    read_step = h.journal.next_or_replay(
        h.run, kind="tool", name="tarot_read", input_fp=h.registry.fingerprint("tarot_read", raw_read)
    )
    read_ctx = ToolContext.from_step(read_step, thread_id="life:self", source_ids=(h.source["id"],))
    read = h.registry.execute("tarot_read", raw_read, read_ctx)
    assert read.ok and read.data["draw"]["id"] == ident
    select_request(h, "foreign-or-missing")
    with pytest.raises(ScopeError):
        h.registry.specs(read_ctx)

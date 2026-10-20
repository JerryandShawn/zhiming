"""Actual PG tarot snapshots bind journal inputs, native cards and source ranges."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.agent.toolkit import ToolContext
from mingjing_core.agent.tools.tarot_parameters import TarotRead, TarotStart
from mingjing_core.application.agent_tarot_lineage import (
    attest_tarot_snapshot,
    cache_id,
)
from mingjing_core.application.agent_tools_contracts import tool_input_fingerprint
from mingjing_core.application.agent_tools_tarot import execute_tarot
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.privacy_maintenance import PrivacyMaintenance
from mingjing_core.domain.contracts import (
    EvidenceError,
    LeaseConflict,
    RevisionConflict,
    ScopeError,
)
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock

from .test_tool_tarot_pg import QUESTION, harness, select_request
from .test_tool_tarot_pg import tarot_env as source_tarot_env
from .test_toolkit_pg import Harness


@pytest.fixture(name="tarot_env")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Any:
    return source_tarot_env.__wrapped__(p2_repo, monkeypatch)


def step_result(h: Harness, *, name: str = "tarot_start", args: dict[str, Any] | None = None) -> tuple[Any, Any, Any]:
    raw = args or {"question": QUESTION, "message_id": h.source["id"], "draw_source": "auto"}
    values = (TarotStart if name == "tarot_start" else TarotRead).model_validate(raw).model_dump()
    step = h.journal.next_or_replay(h.run, kind="tool", name=name, input_fp=tool_input_fingerprint(name, values))
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    return step, ctx, execute_tarot(h.service, name, values, ctx)


def ready_read(h: Harness, *, reading: bool = False) -> tuple[Any, Any, Any]:
    step, _, result = step_result(h)
    h.journal.complete(step, result.model_dump())
    draw_id = result.data["draw"]["id"]
    TarotService(h.repo).reveal("alice", draw_id)
    select_request(h, draw_id)
    if reading:
        row = TarotService(h.repo).begin_reading(
            "alice",
            draw_id,
            model="synthetic",
            prompt_version="synthetic-v1",
            context_snapshot={},
            idempotency_key="synthetic-reading",
        )["reading"]
        with h.repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET request=jsonb_set(request,'{{reading_id}}',%s) WHERE id=%s").format(
                    h.repo.table("core_runs")
                ),
                (Jsonb(row["id"]), h.run["id"]),
            )
        h.run = h.repo.fetch_run("alice", h.run["id"])
    return step_result(h, name="tarot_read", args={"draw_id": draw_id})


def test_completed_snapshot_binds_fixed_hidden_deck_without_inventing_reading(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, ctx, result = step_result(h)
    with pytest.raises(EvidenceError, match="已完成"):
        attest_tarot_snapshot(h.service, h.run, "tarot_start", result)
    h.journal.complete(step, result.model_dump())
    cached = attest_tarot_snapshot(h.service, h.run, "tarot_start", result)
    assert cached["native_reading_id"] is None and cached["reading"] is None
    assert cached["source_refs"][0]["quote"] == QUESTION
    assert cached["versions"] == {"message:" + h.source["id"]: h.source["revision"]}
    assert "message:" + h.source["id"] in h.repo.fetch_run("alice", h.run["id"])["state_version"]
    before = h.repo.get_revision("alice")
    again = execute_tarot(h.service, ctx.name, cached["arguments"], ctx)
    assert again == result and h.repo.get_revision("alice") == before
    assert len(TarotService(h.repo).list_draws("alice")) == 1


def test_revealed_cards_and_actual_optional_reading_are_bound(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, _, result = ready_read(h, reading=True)
    h.journal.complete(step, result.model_dump())
    cached = attest_tarot_snapshot(h.service, h.run, "tarot_read", result)
    assert len(result.data["draw"]["cards"]) == 3 and result.data["draw"]["status"] == "ready"
    assert cached["reading"]["id"] == cached["native_reading_id"]
    assert cached["reading"]["version"] == 1 and cached["reading"]["model"] == "synthetic"


@pytest.mark.parametrize("change", ["result", "native_cards", "native_question", "arguments", "reading"])
def test_mutated_result_native_input_cards_or_reading_fail_closed(tarot_env: Any, change: str) -> None:
    h = harness(tarot_env)
    step, ctx, result = ready_read(h, reading=True)
    h.journal.complete(step, result.model_dump())
    with h.repo.transaction("alice") as connection:
        if change == "result":
            result = result.model_copy(deep=True)
            result.data["registered_aliases"] = {"c999": {"id": "fake"}}
        elif change == "arguments":
            connection.execute(
                sql.SQL("UPDATE {} SET data=jsonb_set(data,'{{arguments,draw_id}}',%s) WHERE id=%s").format(
                    h.repo.table("core_entities")
                ),
                (Jsonb("fake"), cache_id(ctx)),
            )
        elif change == "reading":
            connection.execute(
                sql.SQL("UPDATE {} SET payload=jsonb_set(payload,'{{model}}',%s) WHERE id=%s").format(
                    h.repo.table("tarot_readings")
                ),
                (Jsonb("forged"), h.run["request"]["reading_id"]),
            )
        else:
            path, value = ("{cards,0,card_id}", "fake") if change == "native_cards" else ("{question}", "fake")
            # cards are a viewer projection of selected: mutate its real native field.
            path = "{selected,0,card_id}" if change == "native_cards" else path
            connection.execute(
                sql.SQL("UPDATE {} SET payload=jsonb_set(payload,%s,%s) WHERE id=%s").format(
                    h.repo.table("tarot_draws")
                ),
                (path, Jsonb(value), result.data["draw"]["id"]),
            )
    with pytest.raises((EvidenceError, ScopeError)):
        attest_tarot_snapshot(h.service, h.run, "tarot_read", result)


@pytest.mark.parametrize("change", ["owner", "epoch", "cancel", "message_version", "source_span"])
def test_current_owner_epoch_lease_and_source_range_are_required(tarot_env: Any, change: str) -> None:
    h = harness(tarot_env)
    step, _, result = step_result(h)
    h.journal.complete(step, result.model_dump())
    run = copy.deepcopy(h.run)
    if change == "owner":
        run["owner"] = "bob"
    elif change == "epoch":
        run["retry_epoch"] += 1
    elif change == "cancel":
        with h.repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET cancel_requested_at=now() WHERE id=%s").format(h.repo.table("core_runs")),
                (h.run["id"],),
            )
    elif change == "message_version":
        h.repo.update("alice", "message", h.source["id"], {"synthetic_change": True}, expected_revision=1)
    else:
        with h.repo.transaction("alice") as connection:
            h.repo.revoke(
                connection,
                "alice",
                "source_span",
                "synthetic-range",
                "stopped",
                {
                    "message_id": h.source["id"],
                    "start": 0,
                    "end": 1,
                },
            )
    with pytest.raises((EvidenceError, LeaseConflict, RevisionConflict, ScopeError)):
        attest_tarot_snapshot(h.service, run, "tarot_start", result)


def test_private_start_does_not_write_snapshot_or_native_draw(tarot_env: Any) -> None:
    h = harness(tarot_env)
    raw = TarotStart(question=QUESTION, message_id=h.source["id"]).model_dump()
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="tarot_start", input_fp=tool_input_fingerprint("tarot_start", raw)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    result = execute_tarot(h.service, "tarot_start", raw, replace(ctx, incognito=True))
    assert not result.ok and result.data["code"] == "incognito"
    assert attest_tarot_snapshot(h.service, h.run, "tarot_start", result) is None
    assert h.repo.list("alice", "runtime_step") == [] and TarotService(h.repo).list_draws("alice") == []


def test_source_withdrawal_clears_private_cache_in_same_pg_transaction(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, ctx, result = step_result(h)
    h.journal.complete(step, result.model_dump())
    fact = MemoryService(h.repo).save_fact("alice", "self", h.source["id"], QUESTION, "preference")
    MemoryService(h.repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    cached = h.repo.get("alice", "runtime_step", cache_id(ctx), include_deleted=True)
    assert cached["status"] == "deleted" and QUESTION not in str(cached)
    with pytest.raises((EvidenceError, LeaseConflict, ScopeError)):
        attest_tarot_snapshot(h.service, h.run, "tarot_start", result)


def test_legacy_draw_without_source_refs_remains_readable_but_has_no_attestation(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, _, result = step_result(h)
    h.journal.complete(step, result.model_dump())
    draw_id = result.data["draw"]["id"]
    TarotService(h.repo).reveal("alice", draw_id)
    select_request(h, draw_id)
    with h.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET payload=jsonb_set(payload,'{{context_snapshot}}',%s) WHERE id=%s").format(
                h.repo.table("tarot_draws")
            ),
            (Jsonb({}), draw_id),
        )
    step, ctx, result = step_result(h, name="tarot_read", args={"draw_id": draw_id})
    assert result.ok
    h.journal.complete(step, result.model_dump())
    with pytest.raises(ScopeError):
        h.repo.get("alice", "runtime_step", cache_id(ctx))
    with pytest.raises(ScopeError):
        attest_tarot_snapshot(h.service, h.run, "tarot_read", result)


@pytest.mark.parametrize("authorization", ["options", "redraw"])
def test_option_or_redraw_authorization_has_exact_withdrawable_source_ranges(
    tarot_env: Any, authorization: str
) -> None:
    suffix = "选择甲或乙" if authorization == "options" else "我坚持重新抽牌"
    h = harness(tarot_env, QUESTION + "。" + suffix)
    args = {"question": QUESTION, "message_id": h.source["id"], "draw_source": "auto"}
    args.update(
        {"spread_id": "choice5", "options": {"A": "甲", "B": "乙"}}
        if authorization == "options"
        else {
            "explicit_new": True,
        }
    )
    step, _, result = step_result(h, args=args)
    h.journal.complete(step, result.model_dump())
    cached = attest_tarot_snapshot(h.service, h.run, "tarot_start", result)
    authorized = next(ref for ref in cached["source_refs"] if ref["quote"] != QUESTION)
    with h.repo.transaction("alice") as connection:
        h.repo.revoke(
            connection,
            "alice",
            "source_span",
            "synthetic-authorization",
            "stopped",
            {
                "message_id": h.source["id"],
                "start": authorized["start"],
                "end": authorized["end"],
            },
        )
    with pytest.raises(EvidenceError):
        attest_tarot_snapshot(h.service, h.run, "tarot_start", result)


def test_cache_body_expires_with_existing_thirty_day_private_step_policy(tarot_env: Any, monkeypatch: Any) -> None:
    h = harness(tarot_env)
    step, ctx, result = step_result(h)
    h.journal.complete(step, result.model_dump())
    h.finish()
    with h.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET updated_at=%s WHERE id=%s").format(h.repo.table("core_runs")),
            (h.service.clock.now(), h.run["id"]),
        )
    clock = FrozenClock(h.service.clock.now() + timedelta(days=31))
    monkeypatch.setattr("mingjing_core.application.privacy_maintenance.get_clock", lambda: clock)
    assert PrivacyMaintenance(h.repo).tick()["private_steps"] == 1
    cache = h.repo.get("alice", "runtime_step", cache_id(ctx), include_deleted=True)
    assert cache["status"] == "deleted" and QUESTION not in str(cache)

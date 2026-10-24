"""Legacy fixed draws remain readable without manufacturing professional proof."""

from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.agent.loop_codec import verified_versions
from mingjing_core.application.agent_tarot_lineage import cache_id
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock
from tools.eval.engine import evaluate_scenario

from .test_eval_v4_pg import case
from .test_eval_v4_pg import target as source_target_fixture
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_tarot_snapshot_lineage_pg import ready_read, step_result
from .test_tool_tarot_pg import QUESTION, harness, select_request


@pytest.fixture(name="legacy_env")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    yield from ((repo, get_clock()) for repo in source_repo_fixture.__wrapped__(p2_repo, monkeypatch))


@pytest.fixture(name="legacy_target")
def target_fixture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    yield from source_target_fixture.__wrapped__(monkeypatch)


def legacy_read(env: Any) -> tuple[Any, Any, Any]:
    h = harness(env)
    case_row = MemoryService(h.repo).create_case("alice", "self", "合成旧牌", message_id=h.source["id"])
    draw = TarotService(h.repo).create_draw(
        "alice",
        subject_id="self",
        case_id=case_row["id"],
        question=QUESTION,
        spread_id="focus1",
        draw_source="manual",
        manual_cards=[{"card_id": "major-08", "orientation": "upright"}],
        idempotency_key="synthetic-legacy-draw",
        context_snapshot={
            "question_message_id": h.source["id"],
            "source_refs": [{"message_id": h.source["id"], "version": h.source["revision"]}],
        },
    )["draw"]
    TarotService(h.repo).reveal("alice", draw["id"])
    select_request(h, draw["id"])
    step, ctx, result = step_result(h, name="tarot_read", args={"draw_id": draw["id"]})
    h.journal.complete(step, result.model_dump())
    return h, ctx, result


def test_original_ta02_retry_contract_finishes_same_real_reading_without_c_or_r(legacy_target: Any) -> None:
    observed = evaluate_scenario(case("TA02"), legacy_target, target_name="v4")
    assert observed["status"] == "passed" and observed["model_calls"] == 2
    run = legacy_target.repo.fetch_run(legacy_target.owner, legacy_target.run_ids[-1])
    assert run["status"] == "succeeded" and run["result"]["used_claim_ids"] == run["result"]["used_fact_ids"] == []
    for kind in ("artifact", "interpretive_claim"):
        assert legacy_target.repo.list(legacy_target.owner, kind) == []
    draws = legacy_target.tarot.cards.list_draws(legacy_target.owner)
    assert len(draws) == 1 and draws[0]["cards"][0]["card_id"] == "major-08"
    readings = legacy_target.tarot.cards.list_readings(legacy_target.owner, draws[0]["id"])
    assert len(readings) == 1 and readings[0]["status"] == "success"
    assert readings[0]["id"] == legacy_target.tarot.failed_reading == legacy_target.tarot.retry_reading


def test_exact_completed_legacy_read_returns_no_lineage_and_does_not_infer_source_ranges(legacy_env: Any) -> None:
    h, ctx, result = legacy_read(legacy_env)
    assert verified_versions(h.service, h.run, "tarot_read", result) == ({}, [])
    with h.repo.transaction("alice") as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND id=%s").format(h.repo.table("core_entities")),
                ("alice", cache_id(ctx)),
            ).fetchone()
            is None
        )
    assert h.repo.list("alice", "artifact") == h.repo.list("alice", "interpretive_claim") == []


@pytest.mark.parametrize(
    "change", ["result_alias", "owner", "epoch", "lease", "subject", "source_version", "source_span", "native_cards"]
)
def test_legacy_fallback_rejects_changed_scope_source_result_or_native_draw(legacy_env: Any, change: str) -> None:
    h, _, result = legacy_read(legacy_env)
    run = copy.deepcopy(h.run)
    if change == "result_alias":
        result = result.model_copy(deep=True)
        result.data["registered_aliases"] = {"r1": {"id": "fake"}}
    elif change == "owner":
        run["owner"] = "bob"
    elif change == "epoch":
        run["retry_epoch"] += 1
    elif change == "lease":
        run["lease_token"] = "forged-lease"
    elif change == "subject":
        run["subject"] = "other"
    elif change == "source_version":
        h.repo.update("alice", "message", h.source["id"], {"synthetic_revision": True}, expected_revision=1)
    else:
        with h.repo.transaction("alice") as connection:
            if change == "source_span":
                h.repo.revoke(
                    connection,
                    "alice",
                    "source_span",
                    "synthetic-question",
                    "stopped",
                    {
                        "message_id": h.source["id"],
                        "start": 0,
                        "end": 1,
                    },
                )
            else:
                connection.execute(
                    sql.SQL(
                        "UPDATE {} SET payload=jsonb_set(payload,'{{selected,0,orientation}}',%s) WHERE id=%s"
                    ).format(h.repo.table("tarot_draws")),
                    (Jsonb("reversed"), result.data["draw"]["id"]),
                )
    with pytest.raises(CoreError):
        verified_versions(h.service, run, "tarot_read", result)


@pytest.mark.parametrize("change", ["missing", "deleted", "tampered", "missing_then_legacy_shape"])
def test_new_format_missing_deleted_or_tampered_cache_never_downgrades(legacy_env: Any, change: str) -> None:
    h = harness(legacy_env)
    step, ctx, result = ready_read(h)
    h.journal.complete(step, result.model_dump())
    cache = h.repo.get("alice", "runtime_step", cache_id(ctx))
    if change == "deleted":
        h.repo.delete("alice", "runtime_step", cache["id"], expected_revision=cache["revision"])
    elif change == "tampered":
        h.repo.update("alice", "runtime_step", cache["id"], {"input_fp": "0" * 64}, expected_revision=1)
    else:
        with h.repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE owner=%s AND id=%s").format(h.repo.table("core_entities")),
                ("alice", cache["id"]),
            )
            if change == "missing_then_legacy_shape":
                snapshot = {
                    "question_message_id": h.source["id"],
                    "source_refs": [{"message_id": h.source["id"], "version": h.source["revision"]}],
                }
                connection.execute(
                    sql.SQL("UPDATE {} SET payload=jsonb_set(payload,'{{context_snapshot}}',%s) WHERE id=%s").format(
                        h.repo.table("tarot_draws")
                    ),
                    (Jsonb(snapshot), result.data["draw"]["id"]),
                )
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "tarot_read", result)


def test_failed_read_has_no_professional_proof_or_side_effects(legacy_env: Any) -> None:
    h = harness(legacy_env)
    failed = ToolResult(ok=False, data={"code": "REFERENCE_ERROR"}, summary="合成读取被拒绝")
    assert verified_versions(h.service, h.run, "tarot_read", failed) == ({}, [])
    assert h.repo.list("alice", "runtime_step") == h.repo.list("alice", "artifact") == []

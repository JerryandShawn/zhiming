"""Real Runtime publication cites fixed cards without turning symbols into facts."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.delivery import OutboxService
from mingjing_core.adapters.tarot import TarotService
from mingjing_core.agent.journal import Journal
from mingjing_core.agent.loop_codec import extend_aliases, verified_versions
from mingjing_core.agent.toolkit import ToolContext, ToolRegistry
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.agent_tools_tarot import execute_tarot
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError, EvidenceError, LeaseConflict, ScopeError
from mingjing_core.memory.backfill import backfill
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .backfill_support import remove_reply
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_tarot_snapshot_lineage_pg import ready_read, step_result
from .test_thread_inbox_pg import ingress, set_runtime, submit
from .test_tool_tarot_pg import QUESTION, harness, select_request
from .test_toolkit_pg import setup


@pytest.fixture(name="tarot_env")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    yield from ((repo, get_clock()) for repo in source_repo_fixture.__wrapped__(p2_repo, monkeypatch))


def register(h: Any, step: Any, result: Any) -> tuple[dict, list]:
    h.journal.complete(step, result.model_dump())
    return verified_versions(h.service, h.run, step.name, result)


def runtime_run(env: Any, *, delivery_target: str | None = None) -> tuple[Any, str]:
    original = harness(env)
    step, _, result = step_result(original)
    original.journal.complete(step, result.model_dump())
    draw_id = result.data["draw"]["id"]
    TarotService(original.repo).reveal("alice", draw_id)
    original.finish()
    text = "请用塔罗沿用已揭示的固定牌反思。我喜欢合成早班"
    if delivery_target:
        current = setup(env[0], text, channel="feishu", external_id=delivery_target)
        current.service.clock = env[1]
    else:
        current = harness(env, text)
    select_request(current, draw_id)
    return current, draw_id


def execute_runtime(h: Any, draw: str, *, port: Any = None) -> tuple[dict, Any]:
    port = port or ScriptedPort(
        [
            answer("", [ToolCall("fixed-read", "tarot_read", {"draw_id": draw})]),
            answer("这副固定牌提供的是象征反思〔c1〕〔r1〕，请结合现实条件核对。"),
        ]
    )
    result = AgentRuntime(h.repo, port, SyntheticMeter(), offline=True).execute(
        ConsultationService(h.repo), "alice", h.run["id"], h.run["lease_token"]
    )
    return result, port


def test_ready_native_cards_register_one_artifact_and_symbolic_claims(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, _, result = ready_read(h)
    versions, rows = register(h, step, result)
    aliases: dict[str, Any] = {}
    extend_aliases(aliases, rows)
    assert {key for key in aliases if key.startswith("c")} == {"c1"}
    assert {key for key in aliases if key.startswith("r")} == {"r1", "r2", "r3"}
    assert "case:" + result.data["draw"]["case_id"] in versions
    claims = h.repo.list("alice", "interpretive_claim")
    assert len(claims) == 3 and h.repo.list("alice", "fact") == []
    for row in claims:
        assert row["claim"]["assertion_status"] == "symbolic_reflection" and row["claim"]["not_user_fact"] is True
        assert row["native_reading_id"] is None and "source_refs" not in row
        assert row["source_ranges"] and QUESTION not in str(row)
        assert row["case_id"] is None


def test_unrevealed_deck_never_exposes_hidden_cards_or_professional_aliases(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, _, result = step_result(h)
    _, rows = register(h, step, result)
    assert not any(row["kind"] in {"artifact", "interpretive_claim"} for row in rows)
    assert h.repo.list("alice", "artifact") == [] and h.repo.list("alice", "interpretive_claim") == []


@pytest.mark.parametrize("change", ["claim", "source_ids", "source_ranges", "epoch", "run_id"])
def test_existing_mirror_tampering_cannot_be_adopted(tarot_env: Any, change: str) -> None:
    h = harness(tarot_env)
    step, _, result = ready_read(h)
    register(h, step, result)
    row = h.repo.list("alice", "interpretive_claim")[0]
    value = {
        "claim": {"text": "forged"},
        "source_ids": ["foreign"],
        "source_ranges": [],
        "epoch": 99,
        "run_id": "other",
    }[change]
    h.repo.update("alice", "interpretive_claim", row["id"], {change: value}, expected_revision=row["revision"])
    with pytest.raises((EvidenceError, ScopeError)):
        verified_versions(h.service, h.run, "tarot_read", result)


@pytest.mark.parametrize("change", ["meaning", "version"])
def test_native_card_meaning_is_revalidated_even_after_real_tool_caches_it(tarot_env: Any, change: str) -> None:
    h = harness(tarot_env)
    step, _, result = step_result(h)
    h.journal.complete(step, result.model_dump())
    ident = result.data["draw"]["id"]
    TarotService(h.repo).reveal("alice", ident)
    select_request(h, ident)
    with h.repo.transaction("alice") as connection:
        path = "{selected,0,card_snapshot,upright}" if change == "meaning" else "{meaning_version}"
        connection.execute(
            sql.SQL("UPDATE {} SET payload=jsonb_set(payload,%s,%s) WHERE id=%s").format(h.repo.table("tarot_draws")),
            (path, Jsonb("伪造牌义"), ident),
        )
    step, _, result = step_result(h, name="tarot_read", args={"draw_id": ident})
    h.journal.complete(step, result.model_dump())
    with pytest.raises(EvidenceError):
        verified_versions(h.service, h.run, "tarot_read", result)


def test_repeated_fixed_read_reuses_mirrors_and_does_not_shuffle(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, _, result = ready_read(h)
    _, first = register(h, step, result)
    aliases: dict[str, Any] = {}
    extend_aliases(aliases, first)
    step, _, again = step_result(h, name="tarot_read", args={"draw_id": result.data["draw"]["id"]})
    _, second = register(h, step, again)
    extend_aliases(aliases, second)
    assert first == second and len(aliases) == 5
    assert len(h.repo.list("alice", "artifact")) == 1 and len(h.repo.list("alice", "interpretive_claim")) == 3
    assert len(TarotService(h.repo).list_draws("alice")) == 1


def test_actual_source_withdrawal_clears_card_mirrors_and_cached_inputs(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, _, result = ready_read(h)
    register(h, step, result)
    fact = MemoryService(h.repo).save_fact("alice", "self", h.source["id"], QUESTION, "preference")
    MemoryService(h.repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    assert h.repo.list("alice", "artifact") == [] and h.repo.list("alice", "interpretive_claim") == []
    for row in h.repo.list("alice", "runtime_step", include_deleted=True):
        assert row["status"] == "deleted" and QUESTION not in str(row)
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "tarot_read", result)


def test_unrelated_partial_withdrawal_keeps_fixed_question_runtime_lineage_without_old_body(tarot_env: Any) -> None:
    original = harness(tarot_env, QUESTION + "。我喜欢夜班")
    fact = MemoryService(original.repo).save_fact("alice", "self", original.source["id"], "我喜欢夜班", "preference")
    step, _, result = step_result(original)
    original.journal.complete(step, result.model_dump())
    draw_id = result.data["draw"]["id"]
    TarotService(original.repo).reveal("alice", draw_id)
    MemoryService(original.repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    current = harness(tarot_env, "请用塔罗沿用固定牌反思")
    select_request(current, draw_id)
    result, port = execute_runtime(current, draw_id)
    assert len(result["used_claim_ids"]) == 1 and result["used_fact_ids"] == []
    assert "我喜欢夜班" not in str(result)
    assert all("我喜欢夜班" not in message.content for request in port.requests for message in request["messages"])


def test_cancel_clears_private_cache_and_mirrors_but_keeps_draw_for_u7(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, _, result = ready_read(h)
    _, records = register(h, step, result)
    draw = TarotService(h.repo).cancel("alice", result.data["draw"]["id"])
    assert draw["status"] == "cancelled" and len(TarotService(h.repo).list_draws("alice")) == 1
    for kind in ("runtime_step", "artifact", "interpretive_claim"):
        assert h.repo.list("alice", kind) == []
    assert all(
        h.repo.get("alice", row["kind"], row["id"], include_deleted=True)["status"] == "deleted"
        for row in records
        if row["kind"] != "message"
    )
    with pytest.raises(EvidenceError):
        verified_versions(h.service, h.run, "tarot_read", result)
    h.finish()


def test_cancel_then_delete_still_finds_original_start_run_from_actual_receipt(tarot_env: Any) -> None:
    h = harness(tarot_env)
    step, _, result = step_result(h)
    h.journal.complete(step, result.model_dump())
    ident = result.data["draw"]["id"]
    TarotService(h.repo).cancel("alice", ident)
    h.finish()
    with h.repo.transaction("alice"):
        receipt = TarotService(h.repo).delete("alice", ident)
    assert h.run["id"] in receipt["affected_ids"]
    assert h.repo.fetch_run("alice", h.run["id"])["status"] == "revoked"
    assert h.repo.get("alice", "message", h.source["id"])["content"] == QUESTION


def test_real_private_thread_refuses_even_direct_long_term_read_without_mirrors(tarot_env: Any) -> None:
    original, draw = runtime_run(tarot_env)
    original.finish()
    repo = tarot_env[0]
    set_runtime(repo, "v4")
    intake, thread = ingress(repo, private=True)
    run = repo.claim_run("alice", submit(intake, thread, "请用塔罗沿用固定牌")["id"])
    args = {"draw_id": draw}
    registry, journal = ToolRegistry(AgentToolsService(repo)), Journal(repo, "alice")
    step = journal.next_or_replay(
        run, kind="tool", name="tarot_read", input_fp=registry.fingerprint("tarot_read", args)
    )
    ctx = ToolContext.from_step(
        step, thread_id=thread, incognito=True, source_ids=(run["request"]["source_message_id"],)
    )
    result = execute_tarot(registry.service, "tarot_read", args, ctx)
    assert not result.ok and result.data == {"code": "incognito"}
    journal.complete(step, result.model_dump())
    assert verified_versions(registry.service, run, "tarot_read", result) == ({}, [])
    assert repo.list("alice", "artifact") == [] and repo.list("alice", "interpretive_claim") == []


def test_actual_core4_claims_publish_and_strict_backfill_restores_real_lineage(tarot_env: Any) -> None:
    h, draw = runtime_run(tarot_env)
    result, port = execute_runtime(h, draw)
    assert result["schema"] == "core4.0" and len(result["used_claim_ids"]) == 1 and result["used_fact_ids"] == []
    assert "〔c1〕" in result["text"] and "〔r1〕" in result["text"]
    assert any(
        "fixed_tarot" in message.content and "registered_aliases" in message.content
        for message in port.requests[-1]["messages"]
        if message.role == "tool"
    )
    run = h.repo.fetch_run("alice", h.run["id"])
    remove_reply(h.repo, run)
    replay = backfill(MemoryService(h.repo), "alice", apply=True)
    assert replay["assistant_created"] == 1 and replay["assistant_skipped"] == 0
    replies = [row for row in h.repo.list("alice", "message") if row.get("role") == "assistant"]
    assert len(replies) == 1 and replies[0]["used_claim_ids"] == result["used_claim_ids"]
    assert set(replies[0]["source_ids"]) == {key[8:] for key in run["state_version"] if key.startswith("message:")}


def test_delete_clears_derived_reply_steps_and_mirrors_but_preserves_independent_user_fact(tarot_env: Any) -> None:
    tarot_env[0].bind_channel("alice", "feishu", "ou_syntheticTarot")
    h, draw = runtime_run(tarot_env, delivery_target="ou_syntheticTarot")
    port = ScriptedPort(
        [
            answer(
                "",
                [
                    ToolCall(
                        "independent-fact",
                        "memory_write",
                        {
                            "message_id": h.source["id"],
                            "quote": "我喜欢合成早班",
                            "summary": "合成独立偏好",
                            "kind": "preference",
                        },
                    )
                ],
            ),
            answer("", [ToolCall("fixed-read", "tarot_read", {"draw_id": draw})]),
            answer("这是象征反思〔r1〕"),
        ]
    )
    result, _ = execute_runtime(h, draw, port=port)
    fact = next(receipt for receipt in result["receipts"] if receipt.get("kind") == "fact")
    outbox = OutboxService(h.repo)
    delivery = outbox.prepare_delivery(
        owner="alice",
        run_id=h.run["id"],
        business_id="synthetic-tarot-delete",
        channel="feishu",
        target="ou_syntheticTarot",
    )
    original_ids = {row["id"] for row in h.repo.list("alice", "message") if row.get("role") == "user"}
    with h.repo.transaction("alice"):
        receipt = TarotService(h.repo).delete("alice", draw)
    assert h.run["id"] in receipt["affected_ids"] and result["message_id"] not in {
        row["id"] for row in h.repo.list("alice", "message")
    }
    assert {row["id"] for row in h.repo.list("alice", "message") if row.get("role") == "user"} == original_ids
    assert h.repo.get("alice", "fact", fact["id"])["content"] == "我喜欢合成早班"
    run = h.repo.fetch_run("alice", h.run["id"])
    assert run["status"] == "revoked" and run["result"] is None
    for kind in ("runtime_step", "artifact", "interpretive_claim"):
        assert h.repo.list("alice", kind) == []
    with h.repo.transaction("alice") as connection:
        assert all(
            row["output"] is None
            for row in connection.execute(
                sql.SQL("SELECT output FROM {} WHERE run_id=%s").format(h.repo.table("core_run_steps")), (h.run["id"],)
            ).fetchall()
        )
    with pytest.raises(LeaseConflict):
        outbox.claim_delivery(owner="alice", outbox_id=delivery["id"])


def test_native_cancel_between_read_and_final_cannot_publish_stale_cards(tarot_env: Any) -> None:
    h, draw = runtime_run(tarot_env)

    class CancellingPort(ScriptedPort):
        def stream(self, messages: Any, **kwargs: Any) -> Any:
            if self.requests:
                TarotService(h.repo).cancel("alice", draw)
            yield from super().stream(messages, **kwargs)

    port = CancellingPort(
        [
            answer("", [ToolCall("fixed-read", "tarot_read", {"draw_id": draw})]),
            answer("不得发布已取消的牌面〔r1〕"),
        ]
    )
    with pytest.raises(CoreError):
        execute_runtime(h, draw, port=port)
    assert h.repo.fetch_run("alice", h.run["id"])["result"] is None
    assert not any(row.get("role") == "assistant" for row in h.repo.list("alice", "message"))

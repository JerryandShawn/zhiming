"""Optional slot arguments preserve old replay fingerprints and do not enable unproven updates."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from mingjing_core.agent.tools.parameters import MemoryWrite
from mingjing_core.application.agent_tools_contracts import tool_input_fingerprint
from mingjing_core.timekit.clock import FrozenClock
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as base_target
from .test_memory2_slots_pg import slots_repo
from .test_toolkit_pg import setup

LEGACY = dict(
    message_id="current",
    quote="我不吃辣",
    summary="我不吃辣",
    kind="preference",
    start=None,
    end=None,
    case_id=None,
    sensitivity="normal",
    date_expression=None,
    event_at=None,
)


@pytest.fixture(name="tool_repo")
def slot_tool_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return slots_repo.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("slot", [None, "unregistered-slot"])
def test_absent_or_unknown_slot_keeps_all_old_normalized_fields_and_journal_fingerprint(slot: str | None):
    args = MemoryWrite.model_validate(dict(LEGACY, slot=slot))
    assert args.model_dump() == LEGACY
    assert args.model_dump(mode="json") == LEGACY and json.loads(args.model_dump_json()) == LEGACY
    assert tool_input_fingerprint("memory_write", args.model_dump()) == tool_input_fingerprint("memory_write", LEGACY)


def test_no_new_slot_field_keeps_legacy_shape_and_known_slot_changes_the_fingerprint():
    assert MemoryWrite.model_validate(LEGACY).model_dump() == LEGACY
    known = MemoryWrite.model_validate(dict(LEGACY, slot="饮食偏好·辣")).model_dump()
    assert known["slot"] == "spice_preference"
    assert tool_input_fingerprint("memory_write", known) != tool_input_fingerprint("memory_write", LEGACY)
    assert MemoryWrite.model_json_schema()["properties"]["slot"]


@pytest.mark.parametrize("slot", [True, 1, ["spice_preference"]])
def test_slot_cannot_supply_non_text_authority(slot: Any):
    with pytest.raises(ValidationError):
        MemoryWrite.model_validate(dict(LEGACY, slot=slot))


@pytest.mark.parametrize(
    "slot,text",
    [("spice_preference", "我不吃辣"), ("residence_city", "我现在住在杭州"), ("sleep_schedule", "我习惯早睡早起")],
)
def test_first_known_slot_persists_actual_metadata_and_saved_receipt(tool_repo: Any, slot: str, text: str):
    h = setup(tool_repo, text)
    result, ctx, args = h.write("preference", slot=slot)
    assert result.ok and result.receipt["write_status"] == "saved"
    row = tool_repo.get("alice", "fact", result.receipt["fact_id"])
    assert row["slot"] == slot and row["content"] == text and row["valid_to"] is None
    assert h.registry.execute("memory_write", args, ctx).receipt == result.receipt
    h.finish()


def test_new_current_value_is_not_written_until_strict_update_proof_is_available(tool_repo: Any):
    h = setup(tool_repo, "我不吃辣")
    first, _, _ = h.write("preference", slot="spice_preference")
    h.finish()
    old = tool_repo.get("alice", "fact", first.receipt["fact_id"])
    h = setup(tool_repo, "最近开始能吃点辣了")
    blocked, _, _ = h.write("preference", slot="spice_preference")
    assert not blocked.ok and blocked.receipt == {
        "write_status": "needs_confirmation",
        "code": "slot_update_requires_commit_proof",
    }
    assert tool_repo.get("alice", "fact", old["id"]) == old
    assert [r["id"] for r in h.service.memory.facts("alice")] == [old["id"]]
    assert len(tool_repo.list("alice", "fact")) == 1
    h.finish()


def test_exact_repeated_fact_in_same_slot_still_uses_real_merge_and_original_sources(tool_repo: Any):
    first = setup(tool_repo, "我不吃辣")
    saved, _, _ = first.write("preference", slot="spice_preference")
    first.finish()
    second = setup(tool_repo, "我不吃辣")
    merged, _, _ = second.write("preference", slot="spice_preference")
    assert merged.ok and merged.receipt["fact_id"] == saved.receipt["fact_id"]
    assert merged.receipt["code"] == "memory2_merged"
    row = tool_repo.get("alice", "fact", merged.receipt["fact_id"])
    assert {ref["message_id"] for ref in row["source_refs"]} == {first.source["id"], second.source["id"]}
    assert len(second.service.memory.facts("alice")) == 1
    second.finish()


def test_multi_slot_values_can_coexist_without_update_receipt(tool_repo: Any):
    for text in ("我喜欢跑步", "我喜欢游泳"):
        h = setup(tool_repo, text)
        saved, _, _ = h.write("preference", slot="hobbies")
        assert saved.ok and saved.receipt["write_status"] == "saved"
        h.finish()
    assert len([r for r in tool_repo.list("alice", "fact") if r.get("slot") == "hobbies"]) == 2


@pytest.mark.parametrize("text", ["我下周在上海出差", "我临时搬到上海住一周", "如果我搬到上海会怎样？"])
def test_transient_or_hypothetical_cannot_write_a_durable_city_slot(tool_repo: Any, text: str):
    h = setup(tool_repo, text)
    result, _, _ = h.write("background", slot="residence_city")
    assert not result.ok and result.receipt["write_status"] in {"rejected", "needs_confirmation"}
    assert tool_repo.list("alice", "fact") == []
    h.finish()


def test_unknown_slot_is_omitted_and_no_slot_is_inferred_from_city_words(tool_repo: Any):
    h = setup(tool_repo, "我现在住在杭州")
    result, _, _ = h.write("background", slot="unknown-city")
    assert result.ok and "slot" not in tool_repo.get("alice", "fact", result.receipt["fact_id"])
    h.finish()


def test_sensitive_slot_still_produces_the_same_p3_pending_without_implicit_consent(tool_repo: Any):
    h = setup(tool_repo, "我最近失眠，改为晚睡")
    pending, _, _ = h.write("background", slot="sleep_schedule")
    assert not pending.ok and pending.receipt["write_status"] == "pending_confirmation"
    assert tool_repo.get("alice", "proposal", pending.receipt["id"])["status"] == "pending"
    assert tool_repo.list("alice", "fact") == [] and tool_repo.list("alice", "consent") == []
    h.finish()


@pytest.fixture(name="target")
def actual_runtime_target(monkeypatch):
    monkeypatch.setattr(
        "mingjing_core.timekit.clock._clock", FrozenClock(datetime.fromisoformat("2026-10-24T03:31:00+08:00"))
    )
    yield from base_target.__wrapped__(monkeypatch)


def test_initial_slot_passes_real_agent_commit_without_relaxing_saved_proof(target: V4Target):
    target.reset(
        {
            "synthetic": True,
            "_scenario_id": "slot-initial-runtime",
            "_scripted": [
                {
                    "turn": 1,
                    "model": [
                        {
                            "tool_call": {
                                "name": "memory_write",
                                "arguments": dict(
                                    message_id="turn-1",
                                    quote="我不吃辣",
                                    summary="我不吃辣",
                                    kind="preference",
                                    slot="spice_preference",
                                ),
                            }
                        },
                        {"text": "记下了，你不吃辣。"},
                    ],
                },
            ],
        }
    )
    result = target.send({"_index": 1, "user": "我不吃辣"})
    assert result.error is None and len(result.receipts) == 1
    receipt = result.receipts[0]
    assert receipt["write_status"] == "saved"
    run = target.repo.fetch_run(target.owner, target.run_ids[-1])
    assert run["status"] == "succeeded" and run["result"]["receipts"] == result.receipts
    fact = target.repo.get(target.owner, "fact", receipt["fact_id"])
    assert fact["slot"] == "spice_preference" and fact["revision"] == receipt["revision"]
    assert fact["source_refs"][0]["message_id"] == target.bindings["turn-1"]
    assert target.case_evidence()["external_provider_requests"] == 0


def test_new_slot_does_not_silence_conflict_with_a_legacy_unslotted_fact(tool_repo: Any):
    first = setup(tool_repo, "我不喜欢吃辣")
    old, _, _ = first.write("preference")
    first.finish()
    second = setup(tool_repo, "我喜欢吃辣")
    pending, _, _ = second.write("preference", slot="spice_preference")
    assert not pending.ok and pending.receipt["code"] == "memory2_possible_conflict"
    assert second.service.memory.facts("alice")[0]["id"] == old.receipt["fact_id"]
    assert len(tool_repo.list("alice", "fact")) == 1
    second.finish()


def test_legacy_unslotted_compatible_statement_is_only_a_guard_and_is_never_relabelled(tool_repo: Any):
    first = setup(tool_repo, "我不吃辣")
    saved, _, _ = first.write("preference")
    first.finish()
    original = tool_repo.get("alice", "fact", saved.receipt["fact_id"])
    second = setup(tool_repo, "我喜欢吃辣")
    guarded, _, _ = second.write("preference", slot="spice_preference")
    assert not guarded.ok and guarded.receipt["code"] == "slot_update_requires_commit_proof"
    assert tool_repo.get("alice", "fact", original["id"]) == original
    assert "slot" not in original and len(tool_repo.list("alice", "fact")) == 1
    second.finish()

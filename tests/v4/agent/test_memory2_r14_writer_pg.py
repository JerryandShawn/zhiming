"""Document 41: actual memory_write effects, not service-only acceptance claims."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from mingjing_core.memory.change_signals import explicit_replacement_slot

from .test_memory2_conflict_resolution_pg import choose, undo
from .test_memory2_slots_pg import slots_repo
from .test_memory2_slots_pg import undo as undo_slot
from .test_toolkit_pg import setup

EXAMPLES = [
    ("我在杭州工作", "我搬到上海了，最近挺忙", "residence_city"),
    ("我不吃辣", "最近开始能吃点辣了", "spice_preference"),
    ("我入职合成甲公司", "我换工作了，现在入职合成乙公司", "employer"),
    ("我担任合成教师", "我现在转岗做合成设计师", "job_role"),
    ("我单身", "我结婚了", "relationship_status"),
    ("我习惯早睡早起", "我现在改为晚睡", "sleep_schedule"),
    ("我喜欢合成跑步", "我不再喜欢合成跑步", "preference"),
    ("我喜欢合成徒步", "我以前喜欢合成徒步，现在不喜欢合成徒步", "preference"),
]


@pytest.fixture(name="tool_repo")
def writer_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return slots_repo.__wrapped__(p2_repo, monkeypatch)


def write_at(repo: Any, monkeypatch: pytest.MonkeyPatch, text: str, day: int, **args: Any):
    instant = datetime.fromisoformat(f"2026-10-{day:02}T10:30:00+08:00")
    monkeypatch.setattr(f"{setup.__module__}.SAID_AT", instant)
    h = setup(repo, text)
    result, ctx, actual_args = h.write(args.pop("kind", "preference"), **args)
    return h, result, ctx, actual_args


@pytest.mark.parametrize("before,after,slot", EXAMPLES)
def test_real_writer_updates_history_replays_and_undoes(tool_repo, monkeypatch, before, after, slot):
    h, saved, _, _ = write_at(tool_repo, monkeypatch, before, 3)
    old = tool_repo.get("alice", "fact", saved.receipt["fact_id"])
    h.finish()
    h, result, ctx, args = write_at(tool_repo, monkeypatch, after, 10)
    assert result.ok and result.receipt["write_status"] == "updated"
    assert result.receipt["affected_ids"] == [old["id"]]
    fresh = tool_repo.get("alice", "fact", result.receipt["fact_id"])
    assert fresh["slot"] == slot and fresh["supersedes"] == old["id"]
    assert [row["id"] for row in h.service.memory.facts("alice")] == [fresh["id"]]
    revision = tool_repo.get_revision("alice")
    assert h.registry.execute("memory_write", args, ctx).receipt == result.receipt
    assert tool_repo.get_revision("alice") == revision
    undo_slot(tool_repo, result.receipt)
    assert h.service.memory.facts("alice")[0]["content"] == before
    assert not h.registry.execute("memory_write", args, ctx).ok
    h.finish()


@pytest.mark.parametrize("before,after,slot", EXAMPLES)
@pytest.mark.parametrize("prefix", ["如果", "听说", "我朋友说：", "临时"])
def test_change_signal_counterexamples_are_not_implicit_updates(before, after, slot, prefix):
    assert explicit_replacement_slot(before, prefix + after) is None


@pytest.mark.parametrize("choice", ["old", "new"])
def test_q06_tool_write_generates_pending_and_explicit_selection_undo(tool_repo, monkeypatch, choice):
    h, first, _, _ = write_at(tool_repo, monkeypatch, "我在杭州工作", 3, kind="background")
    h.finish()
    h, pending, _, _ = write_at(tool_repo, monkeypatch, "我在上海上班", 10, kind="background")
    assert pending.receipt["code"] == "memory2_possible_conflict" and not pending.ok
    assert len(h.service.memory.facts("alice")) == 1
    old = tool_repo.get("alice", "fact", first.receipt["fact_id"])
    selected = choose(h, pending, choice)
    assert selected["write_status"] == ("updated" if choice == "new" else "stopped")
    assert len(h.service.memory.facts("alice")) == 1
    undo(h, pending)
    assert h.service.memory.facts("alice")[0]["id"] == old["id"]
    h.finish()


def test_invalid_optional_slot_saves_without_the_slot(tool_repo, monkeypatch):
    h, result, _, _ = write_at(tool_repo, monkeypatch, "我在上海上班", 3, slot="residence_city")
    assert result.ok and result.receipt["code"] == "slot_ignored"
    assert not tool_repo.get("alice", "fact", result.receipt["fact_id"]).get("slot")
    h.finish()


def test_sensitive_change_still_requires_sensitive_confirmation(tool_repo, monkeypatch):
    h, pending, _, _ = write_at(tool_repo, monkeypatch, "我因失眠现在改为晚睡", 10, slot="sleep_schedule")
    assert pending.receipt["code"] == "sensitive_confirmation"
    assert not pending.ok and not tool_repo.list("alice", "fact")
    h.finish()


def test_change_in_another_domain_is_not_preference_authority():
    assert explicit_replacement_slot("我喜欢合成跑步", "我换工作了，我不喜欢合成跑步") is None


def test_slot_ignored_merge_still_checks_undo_proof_on_replay(tool_repo, monkeypatch):
    from .test_memory2_merge_pg import undo as undo_merge

    h, _, _, _ = write_at(tool_repo, monkeypatch, "我在上海上班", 3, kind="background")
    h.finish()
    h, merged, ctx, args = write_at(
        tool_repo, monkeypatch, "我在上海上班", 10, kind="background", slot="residence_city"
    )
    assert merged.ok and merged.receipt["code"] == "slot_ignored" and merged.receipt["ids"]
    undo_merge(tool_repo, merged)
    assert not h.registry.execute("memory_write", args, ctx).ok
    h.finish()

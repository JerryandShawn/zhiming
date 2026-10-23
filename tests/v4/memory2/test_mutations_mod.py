"""Pure module checks use synthetic statements and no external services."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.memory.slots import SLOT_DEFINITIONS, normalize_slot
from mingjing_core.memory2.conflicts import possible_conflicts
from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.memory2.dedup import equivalent
from mingjing_core.memory2.forget import plan_forget
from mingjing_core.memory2.guards import MemoryGuardError, authorize_fact
from mingjing_core.memory2.mutation_contracts import FactChange, MutationConflict
from mingjing_core.memory2.mutations import apply_plan, plan_changes, plan_write
from mingjing_core.memory2.plan_builder import seal
from mingjing_core.memory2.undo import undo_plan
from mingjing_core.timekit.clock import FrozenClock

NOW = datetime(2026, 10, 21, 0, tzinfo=UTC)
SCOPE = MemoryScope("synthetic-owner", "synthetic-self")
CLOCK = FrozenClock(NOW)


def fact(identifier="a", text="我住杭州", *, day=2, slot=None, value=None):
    at = NOW - timedelta(days=day)
    source = MemorySource(f"source-{identifier}", SCOPE.owner_id, SCOPE.subject_id, text, at)
    anchor = SourceAnchor(source.id, 1, 0, len(text), text)
    item = MemoryFact(
        identifier,
        SCOPE.owner_id,
        SCOPE.subject_id,
        "background",
        text,
        (source.id,),
        at,
        NOW,
        (anchor,),
        slot=slot,
        value=value,
    )
    return item, source


def state(*items):
    return MemorySnapshot(SCOPE, facts=tuple(item[0] for item in items), sources=tuple(item[1] for item in items))


def update_pair(slot="residence_city"):
    old, first = fact(slot=slot, value="旧值")
    new, second = fact("b", "我现在常住新值", day=1, slot=slot, value="新值")
    snapshot = replace(state((old, first)), sources=(first, second))
    plan = plan_write(snapshot, new, scope=SCOPE, operation_id="write", clock=CLOCK)
    return snapshot, old, new, plan, apply_plan(snapshot, plan).snapshot


@pytest.mark.parametrize("slot", [item.name for item in SLOT_DEFINITIONS if item.cardinality == "single"])
def test_all_single_slots_keep_history_and_undo_all_fields(slot):
    _, old, new, plan, written = update_pair(slot)
    assert plan.write_status == "updated"
    assert written.fact(old.id).valid_to == new.said_at
    assert written.fact(old.id).status == "active"
    assert written.fact(new.id).supersedes == old.id
    restored = undo_plan(written, plan, operation_id="undo").snapshot
    assert restored.fact(old.id) == old
    assert restored.fact(new.id).status == "retired"


@pytest.mark.parametrize(
    "text",
    [
        "去上海出差一周",
        "到上海旅游",
        "上海探亲",
        "在上海暂住",
        "上海短住",
        "上海过夜",
        "途经上海中转",
        "上海借住",
        "去上海度假",
        "上海路过",
    ],
)
def test_temporary_city_is_separate_event(text):
    old, source = fact(slot="residence_city", value="杭州")
    new, other = fact("b", text, day=1, slot="residence_city", value="上海")
    snapshot = replace(state((old, source)), sources=(source, other))
    plan = plan_write(snapshot, new, scope=SCOPE, operation_id="temporary", clock=CLOCK)
    written = apply_plan(snapshot, plan).snapshot
    assert written.fact(old.id) == old
    assert written.fact(new.id).slot is None
    assert normalize_slot("invented-slot") is None


@pytest.mark.parametrize("text", ["我不住上海", "我以前住上海", "我的朋友现在常住上海"])
def test_noncurrent_or_other_person_city_does_not_overwrite(text):
    old, source = fact(slot="residence_city", value="杭州")
    new, other = fact("b", text, day=1, slot="residence_city", value="上海")
    snapshot = replace(state((old, source)), sources=(source, other))
    plan = plan_write(snapshot, new, scope=SCOPE, operation_id="negative-city", clock=CLOCK)
    assert apply_plan(snapshot, plan).snapshot.fact(old.id) == old


def test_replay_same_plan_and_reject_other_payload():
    initial, _, _, plan, written = update_pair()
    replay = apply_plan(written, plan)
    assert replay.replayed and replay.snapshot == written
    different = seal(replace(plan, summary="different"))
    with pytest.raises(MutationConflict, match="operation_payload_changed"):
        apply_plan(written, different)
    with pytest.raises(MutationConflict, match="snapshot_revision_changed"):
        apply_plan(replace(initial, revision=1), plan)


def test_replay_after_undo_does_not_resurrect():
    _, _, new, plan, written = update_pair()
    outcome = undo_plan(written, plan, operation_id="undo")
    assert undo_plan(outcome.snapshot, plan, operation_id="undo").replayed
    again = apply_plan(outcome.snapshot, plan)
    assert again.replayed and again.write_status == "undone"
    assert again.snapshot.fact(new.id).status == "retired"


def test_source_epoch_closes_apply_race():
    initial, _, _, plan, _ = update_pair()
    changed = replace(initial, source_epoch=1)
    with pytest.raises(MutationConflict, match="snapshot_revision_changed"):
        apply_plan(changed, plan)


def test_replay_after_source_revocation_cannot_claim_saved():
    _, _, _, plan, written = update_pair()
    sources = tuple(replace(source, revoked=True) for source in written.sources)
    revoked = replace(written, sources=sources, source_epoch=1)
    replay = apply_plan(revoked, plan)
    assert replay.replayed and replay.write_status == "unavailable"


def test_undo_preserves_later_edited_fields():
    _, old, _, plan, written = update_pair()
    edited = replace(written.fact(old.id), pinned=True, text="后来人工编辑的合成文本", revision=3)
    later = replace(written, facts=(edited, written.fact("b")), revision=written.revision + 1)
    restored = undo_plan(later, plan, operation_id="undo")
    assert restored.snapshot.fact(old.id).pinned
    assert restored.snapshot.fact(old.id).text == edited.text
    assert restored.snapshot.fact(old.id).valid_to is None
    assert f"{old.id}.revision" in restored.conflicts


def test_undo_and_forget_do_not_revive_revoked_origin():
    _, old, _, plan, written = update_pair()
    revoked = replace(written.sources[0], revoked=True)
    current = replace(written, sources=(revoked, written.sources[1]), source_epoch=1)
    restored = undo_plan(current, plan, operation_id="undo")
    assert restored.snapshot.fact(old.id).valid_to is not None
    assert "a.source_unavailable" in restored.conflicts
    forget = plan_forget(current, "b", scope=SCOPE, operation_id="forget")
    after = apply_plan(current, forget).snapshot
    assert after.fact(old.id).valid_to is not None
    assert after.fact("b").status == "deleted"


def test_forget_both_chain_ends_and_no_undo_resurrection():
    _, old, _, _, written = update_pair()
    forget_new = plan_forget(written, "b", scope=SCOPE, operation_id="forget-new")
    restored = apply_plan(written, forget_new).snapshot
    assert restored.fact(old.id).valid_to is None
    assert restored.fact(old.id).superseded_by is None
    assert restored.fact("b").text == "已遗忘"
    with pytest.raises(MutationConflict, match="forgotten_content"):
        undo_plan(restored, forget_new, operation_id="unsafe-undo")
    forget_old = plan_forget(written, "a", scope=SCOPE, operation_id="forget-old")
    after = apply_plan(written, forget_old).snapshot
    assert after.fact("b").supersedes is None
    assert after.fact("b").status == "active"


def test_exact_merge_keeps_all_source_anchors_and_undo():
    old, source = fact()
    new, other = fact("b", old.text, day=1)
    snapshot = replace(state((old, source)), sources=(source, other))
    plan = plan_write(snapshot, new, scope=SCOPE, operation_id="merge", clock=CLOCK)
    assert plan.write_status == "merged"
    merged = apply_plan(snapshot, plan).snapshot
    assert merged.fact(old.id).source_ids == (source.id, other.id)
    assert len(merged.fact(old.id).anchors) == 2
    assert undo_plan(merged, plan, operation_id="undo").snapshot.fact(old.id) == old


def test_out_of_order_undo_never_reopens_predecessor_under_current_descendant():
    _, old, _, first_plan, first = update_pair()
    newest, source = fact("c", "我现在常住终值", day=0, slot="residence_city", value="终值")
    current = replace(first, sources=(*first.sources, source))
    second = plan_write(current, newest, scope=SCOPE, operation_id="next", clock=CLOCK)
    final = apply_plan(current, second).snapshot
    undone = undo_plan(final, first_plan, operation_id="undo-first")
    live = [item for item in undone.snapshot.facts if item.status == "active" and item.valid_to is None]
    assert [item.id for item in live] == [newest.id]
    assert undone.snapshot.fact(old.id).valid_to is not None
    assert "a.later_successor" in undone.conflicts


def test_forget_middle_chain_member_never_reopens_old_predecessor():
    _, old, _, _, first = update_pair()
    newest, source = fact("c", "我现在常住终值", day=0, slot="residence_city", value="终值")
    current = replace(first, sources=(*first.sources, source))
    second = plan_write(current, newest, scope=SCOPE, operation_id="next", clock=CLOCK)
    final = apply_plan(current, second).snapshot
    forget = plan_forget(final, "b", scope=SCOPE, operation_id="forget-middle")
    after = apply_plan(final, forget).snapshot
    assert after.fact(old.id).valid_to is not None
    assert after.fact(newest.id).supersedes is None
    assert after.fact("b").status == "deleted"


@pytest.mark.parametrize(("left", "right"), [("金额1.2万元", "金额12万元"), ("型号A-B", "型号AB"), ("1+2", "12")])
def test_dedup_keeps_semantic_punctuation(left, right):
    before, _ = fact(text=left)
    after, _ = fact("b", right)
    assert not equivalent(before, after)


def test_unslotted_opposition_is_proposal_never_overwrite():
    old, source = fact(text="我喜欢游泳")
    new, other = fact("b", "我不喜欢游泳", day=1)
    snapshot = replace(state((old, source)), sources=(source, other))
    assert possible_conflicts(new, (old,))
    plan = plan_write(snapshot, new, scope=SCOPE, operation_id="possible", clock=CLOCK)
    assert plan.write_status == "possible_conflict" and "以哪个为准" in plan.summary
    assert apply_plan(snapshot, plan).snapshot.facts == (old,)


@pytest.mark.parametrize("change", [{"revoked": True}, {"incognito": True}, {"role": "assistant"}, {"revision": 2}])
def test_source_authority_is_not_a_caller_boolean(change):
    item, source = fact()
    snapshot = MemorySnapshot(SCOPE, sources=(replace(source, **change),))
    with pytest.raises(MemoryGuardError):
        authorize_fact(item, snapshot, SCOPE)


def test_missing_anchor_and_assistant_impersonation_rejected():
    item, source = fact()
    with pytest.raises(MemoryGuardError, match="source_anchor_required"):
        authorize_fact(replace(item, anchors=()), MemorySnapshot(SCOPE, sources=(source,)), SCOPE)
    assistant = replace(item, origin="assistant_claim")
    with pytest.raises(MemoryGuardError, match="assistant_cannot"):
        authorize_fact(assistant, MemorySnapshot(SCOPE, sources=(replace(source, role="assistant"),)), SCOPE)


def test_forged_approved_plan_cannot_change_text_or_insert_sensitive_fact():
    initial, old, _, plan, _ = update_pair()
    unsafe = FactChange(old.id, old, replace(old, text="伪造的额外事实"))
    tampered = seal(replace(plan, changes=(unsafe,)))
    with pytest.raises(MemoryGuardError, match="mutation_content_not_authorized"):
        apply_plan(initial, tampered)
    with pytest.raises(MutationConflict, match="metadata_plan_cannot"):
        plan_changes(initial, (unsafe,), scope=SCOPE, operation_id="metadata")


@pytest.mark.parametrize("kwargs", [{"active": "false"}, {"revoked": 0}, {"revision": True}, {"incognito": None}])
def test_source_typed_boundaries(kwargs):
    _, source = fact()
    with pytest.raises(ValueError):
        replace(source, **kwargs)


def test_snapshot_freezes_lists_and_rejects_duplicate_ids():
    item, source = fact()
    mutable = [item]
    snapshot = MemorySnapshot(SCOPE, facts=mutable, sources=[source])
    mutable.clear()
    assert snapshot.facts == (item,)
    with pytest.raises(ValueError, match="duplicate"):
        MemorySnapshot(SCOPE, facts=(item, item))
    assert item.text not in repr(item)
    assert source.text not in repr(source)

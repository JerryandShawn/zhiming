"""Independent before/after truth, replay races, and supersession lifecycle."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mingjing_core.memory2.contracts import (
    MemoryFact,
    MemoryScope,
    MemorySnapshot,
    MemorySource,
    SourceAnchor,
)
from mingjing_core.memory2.forget import plan_forget
from mingjing_core.memory2.guards import MemoryGuardError
from mingjing_core.memory2.mutation_contracts import FactChange, MutationConflict
from mingjing_core.memory2.mutations import apply_plan, plan_write
from mingjing_core.memory2.plan_builder import seal
from mingjing_core.memory2.undo import undo_plan
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = MemoryScope("owner", "self")
CLOCK = FrozenClock(AT + timedelta(days=1))
TRUTH = json.loads((Path(__file__).parent / "fixtures/acceptance_policy_expected_mod.json").read_text("utf-8"))
SLOTS = (
    ("residence_city", "我现在常住苏州。", "苏州", "我现在常住南京。", "南京"),
    ("employer", "我现在在甲公司工作。", "甲公司", "我已经入职乙公司。", "乙公司"),
    ("occupation", "我现在的职业是教师。", "教师", "我现在转职为编辑。", "编辑"),
    ("relationship_status", "我目前单身。", "单身", "我目前正在恋爱。", "恋爱"),
    ("preferred_name", "请叫我小陆。", "小陆", "以后请叫我阿陆。", "阿陆"),
    ("food_spicy", "我平时不吃辣。", "不辣", "我现在喜欢微辣。", "微辣"),
    ("sleep_routine", "我习惯十一点睡觉。", "23:00", "我改为十点睡觉。", "22:00"),
    ("study_goal", "我今年想学绘画。", "绘画", "我当前学习目标改为钢琴。", "钢琴"),
    ("current_school", "我目前就读甲学校。", "甲学校", "我已经转入乙学校。", "乙学校"),
    (
        "communication_style",
        "我喜欢你回答详细一点。",
        "详细",
        "以后请用简短回答。",
        "简短",
    ),
)


def make_fact(text, identity, *, at=AT, slot=None, value=None, kind="background"):
    source = MemorySource("s-" + identity, "owner", "self", text, at)
    fact = MemoryFact(
        identity,
        "owner",
        "self",
        kind,
        text,
        (source.id,),
        at,
        at,
        anchors=(SourceAnchor(source.id, 1, 0, len(text), text),),
        slot=slot,
        value=value,
    )
    return fact, source


def state_pair(
    slot="residence_city",
    old_text="我现在常住苏州。",
    old_value="苏州",
    new_text="我现在常住南京。",
    new_value="南京",
):
    old, old_source = make_fact(old_text, "old", slot=slot, value=old_value)
    new, new_source = make_fact(new_text, "new", at=AT + timedelta(hours=1), slot=slot, value=new_value)
    snapshot = MemorySnapshot(SCOPE, facts=(old,), sources=(old_source, new_source))
    return snapshot, old, new


def write(snapshot, fact, op="write"):
    return plan_write(snapshot, fact, scope=SCOPE, operation_id=op, clock=CLOCK)


@pytest.mark.parametrize("slot,old_text,old_value,new_text,new_value", SLOTS)
def test_every_single_slot_has_exact_validity_chain_and_lossless_undo(slot, old_text, old_value, new_text, new_value):
    initial, old, new = state_pair(slot, old_text, old_value, new_text, new_value)
    plan = write(initial, new)
    applied = apply_plan(initial, plan).snapshot
    assert applied.fact(old.id).valid_to == new.said_at
    assert applied.fact(old.id).superseded_by == new.id
    assert applied.fact(new.id).supersedes == old.id
    assert applied.fact(new.id).valid_from == new.said_at
    assert applied.fact(old.id).text == old.text
    assert initial.fact(old.id) == old and initial.fact(new.id) is None
    restored = undo_plan(applied, plan, operation_id="undo").snapshot
    assert restored.fact(old.id) == old
    assert restored.fact(new.id).status == "retired"


@pytest.mark.parametrize(
    "text,value",
    list(
        zip(
            TRUTH["temporary_states"],
            [
                "上海",
                "苏州",
                "杭州",
                "北京",
                "广州",
                "朋友家",
                "南京",
                "成都",
                "隔壁组",
                "晚睡",
            ],
            strict=True,
        )
    ),
)
def test_temporary_status_does_not_change_existing_residence(text, value):
    initial, old, incoming = state_pair(new_text=text, new_value=value)
    outcome = apply_plan(initial, write(initial, incoming))
    assert outcome.snapshot.fact(old.id) == old
    added = outcome.snapshot.fact(incoming.id)
    assert added is not None and added.slot is None
    assert added.supersedes is None and added.text == text


@pytest.mark.parametrize("text", ["我已经搬到上海了。", "我明天搬去上海长期住。"])
def test_persistent_move_remains_an_update_even_with_relative_time(text):
    initial, old, incoming = state_pair(new_text=text, new_value="上海")
    result = apply_plan(initial, write(initial, incoming))
    assert result.write_status == "updated"
    assert result.snapshot.fact(old.id).valid_to == incoming.said_at
    assert result.snapshot.fact(incoming.id).supersedes == old.id


@pytest.mark.parametrize("slot", ["important_people", "hobbies", "unregistered_slot"])
def test_multi_or_unknown_slot_addition_never_overwrites_previous(slot):
    initial, old, incoming = state_pair(slot, "我很重视小组合作。", "合作", "我也喜欢独处阅读。", "阅读")
    outcome = apply_plan(initial, write(initial, incoming)).snapshot
    assert outcome.fact(old.id) == old
    assert outcome.fact(incoming.id).supersedes is None


def test_repeated_fact_merges_sources_without_duplicate_or_information_loss():
    old, source1 = make_fact("我喜欢清晨去公园散步。", "first")
    new, source2 = make_fact(old.text, "second", at=AT + timedelta(hours=1))
    original = MemorySnapshot(SCOPE, facts=(old,), sources=(source1, source2))
    plan = write(original, new)
    updated = apply_plan(original, plan).snapshot
    live = [fact for fact in updated.facts if fact.status == "active"]
    assert len(live) == 1
    assert set(live[0].source_ids) == {source1.id, source2.id}
    assert {anchor.source_id for anchor in live[0].anchors} == {source1.id, source2.id}
    assert undo_plan(updated, plan, operation_id="undo").snapshot.fact(old.id) == old


def test_two_competing_plans_require_replanning_and_same_operation_replay_is_idempotent():
    initial, _, new = state_pair()
    plan = write(initial, new, "same")
    competitor = write(initial, replace(new, id="competitor"), "other")
    applied = apply_plan(initial, plan)
    replay = apply_plan(applied.snapshot, plan)
    assert replay.replayed and replay.snapshot == applied.snapshot
    with pytest.raises(MutationConflict):
        apply_plan(applied.snapshot, competitor)
    changed_payload = write(initial, replace(new, text=new.text + "我已确认。"), "same")
    with pytest.raises(MutationConflict):
        apply_plan(applied.snapshot, changed_payload)


def test_replayed_write_after_undo_stays_undone_and_second_undo_does_not_resurrect():
    initial, old, incoming = state_pair()
    plan = write(initial, incoming)
    applied = apply_plan(initial, plan).snapshot
    undone = undo_plan(applied, plan, operation_id="undo")
    repeated = undo_plan(undone.snapshot, plan, operation_id="undo")
    assert repeated.replayed and repeated.snapshot == undone.snapshot
    replay = apply_plan(undone.snapshot, plan)
    assert replay.replayed and replay.write_status == "undone"
    assert replay.snapshot.fact(old.id) == old
    assert replay.snapshot.fact(incoming.id).status == "retired"


def test_later_edited_fields_survive_undo_with_explicit_conflict():
    initial, old, incoming = state_pair()
    plan = write(initial, incoming)
    applied = apply_plan(initial, plan).snapshot
    changed = replace(applied.fact(old.id), valid_to=AT + timedelta(days=3), pinned=True, edited=True)
    later = replace(
        applied,
        facts=(changed, applied.fact(incoming.id)),
        revision=applied.revision + 1,
    )
    undone = undo_plan(later, plan, operation_id="undo")
    kept = undone.snapshot.fact(old.id)
    assert kept.valid_to == changed.valid_to and kept.pinned and kept.edited
    assert any("valid_to" in conflict for conflict in undone.conflicts)
    assert initial.fact(old.id) == old


@pytest.mark.parametrize("withdraw", ["revoked", "inactive", "revision", "incognito", "optout"])
def test_prepared_write_fails_after_source_epoch_and_undo_never_revives_revoked_predecessor(
    withdraw,
):
    initial, old, incoming = state_pair()
    plan = write(initial, incoming)
    applied = apply_plan(initial, plan).snapshot
    values = {
        "revoked": {"revoked": True},
        "inactive": {"active": False},
        "revision": {"revision": 2},
        "incognito": {"incognito": True},
        "optout": {"optout": True},
    }[withdraw]
    sources = (replace(initial.sources[0], **values), initial.sources[1])
    invalid = replace(initial, sources=sources, source_epoch=1, revision=1)
    with pytest.raises(MutationConflict):
        apply_plan(invalid, plan)
    late = replace(applied, sources=sources, source_epoch=1, revision=applied.revision + 1)
    undone = undo_plan(late, plan, operation_id="undo")
    assert undone.snapshot.fact(old.id).valid_to is not None
    assert undone.conflicts


@pytest.mark.parametrize("end", ["old", "new"])
def test_forget_detaches_both_chain_directions_and_cannot_be_undone(end):
    initial, old, incoming = state_pair()
    plan = write(initial, incoming)
    applied = apply_plan(initial, plan).snapshot
    forget = plan_forget(applied, end, scope=SCOPE, operation_id="forget")
    forgotten = apply_plan(applied, forget).snapshot
    target = forgotten.fact(end)
    assert target.status == "deleted" and not target.source_ids and not target.anchors
    assert target.value is None and not target.source_valid
    assert all(fact.supersedes != end and fact.superseded_by != end for fact in forgotten.facts)
    if end == "new":
        assert forgotten.fact(old.id).valid_to is None
    else:
        assert forgotten.fact(incoming.id).status == "active"
    with pytest.raises(MutationConflict):
        undo_plan(forgotten, forget, operation_id="undo-forget")
    later_undo = undo_plan(forgotten, plan, operation_id="undo-write").snapshot
    assert later_undo.fact(end).status == "deleted"


def test_forgetting_new_does_not_restore_revoked_predecessor():
    initial, old, incoming = state_pair()
    applied = apply_plan(initial, write(initial, incoming)).snapshot
    state = replace(
        applied,
        sources=(replace(initial.sources[0], revoked=True), initial.sources[1]),
        source_epoch=1,
        revision=applied.revision + 1,
    )
    result = apply_plan(state, plan_forget(state, incoming.id, scope=SCOPE, operation_id="forget")).snapshot
    assert result.fact(old.id).valid_to is not None
    assert result.fact(incoming.id).status == "deleted"


def test_undo_of_never_applied_plan_and_scope_forgery_are_rejected():
    initial, _, incoming = state_pair()
    plan = write(initial, incoming)
    with pytest.raises(MutationConflict):
        undo_plan(initial, plan, operation_id="undo")
    with pytest.raises(MemoryGuardError):
        plan_forget(initial, "old", scope=MemoryScope("intruder", "self"), operation_id="forget")


def test_possible_contradiction_is_a_question_without_writing_either_fact():
    old, first_source = make_fact("我喜欢和同事一起吃午饭。", "old", kind="preference")
    new, second_source = make_fact("我不喜欢和同事一起吃午饭。", "new", kind="preference")
    initial = MemorySnapshot(SCOPE, facts=(old,), sources=(first_source, second_source))
    plan = write(initial, new)
    assert plan.write_status == "possible_conflict" and not plan.changes
    assert all(part in plan.summary for part in ("以前你说", old.text, "现在说", new.text, "以哪个为准"))
    assert apply_plan(initial, plan).snapshot.facts == (old,)


def test_resealed_plan_cannot_invent_content_or_skip_sensitive_confirmation():
    initial, _, new = state_pair()
    plan = write(initial, new)
    change = plan.changes[-1]
    forged_change = replace(change, after=replace(change.after, text="用户已经同意完全相反的事实。"))
    forged = seal(replace(plan, changes=(*plan.changes[:-1], forged_change)))
    with pytest.raises(MemoryGuardError):
        apply_plan(initial, forged)
    private, source = make_fact("我确诊了哮喘。", "private")
    private_state = MemorySnapshot(SCOPE, sources=(source,))
    proposal = write(private_state, private)
    forged = seal(
        replace(
            proposal,
            changes=(FactChange(private.id, None, private),),
            write_status="saved",
            policy_action="save",
        )
    )
    with pytest.raises(MemoryGuardError):
        apply_plan(private_state, forged)


@pytest.mark.parametrize("flag,value", [("revoked", True), ("active", False), ("revision", 2)])
def test_source_authentication_is_rechecked_even_if_external_caller_forgets_epoch(flag, value):
    initial, _, incoming = state_pair()
    plan = write(initial, incoming)
    sources = (initial.sources[0], replace(initial.sources[1], **{flag: value}))
    with pytest.raises(MemoryGuardError):
        apply_plan(replace(initial, sources=sources), plan)


def test_replay_after_source_withdrawal_reports_unavailable_without_reviving():
    initial, _, incoming = state_pair()
    plan = write(initial, incoming)
    applied = apply_plan(initial, plan).snapshot
    revoked = replace(
        applied,
        sources=(initial.sources[0], replace(initial.sources[1], revoked=True)),
        source_epoch=1,
        revision=applied.revision + 1,
    )
    replayed = apply_plan(revoked, plan)
    assert replayed.replayed and replayed.write_status == "unavailable"
    assert replayed.snapshot == revoked

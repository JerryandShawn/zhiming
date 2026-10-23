"""Synthetic, offline review plans preserve raw records and require current scope/source authority."""

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.organize._change_values import FieldValue
from mingjing_core.organize.changes import MemoryChangeStore
from mingjing_core.organize.supplement_v2 import (
    EntityRecord,
    ReviewApproval,
    SensitiveGrant,
    SupplementConflict,
    SupplementSnapshot,
    TopicRecord,
    build_review_proposal,
    entity_from_fact,
    evidence_fingerprint,
    plan_archive_review,
    plan_review_labels,
    plan_topic_archive,
    project_plan,
    project_undo,
    propose_case_upgrade,
    review_data,
    to_legacy_changeset,
)
from mingjing_core.organize.supplement_v2.plan_contracts import seal_plan
from mingjing_core.organize.v2.contracts import AREA_IDS, Prediction
from mingjing_core.timekit.clock import FrozenClock

SCOPE = MemoryScope("synthetic-owner", "self")
AT = datetime(2026, 10, 17, 2, tzinfo=UTC)


def fixture(kind="fact", text="合成的学习安排", labels=None):
    role = "assistant" if kind == "note" else "user"
    source = MemorySource("entity", SCOPE.owner_id, SCOPE.subject_id, text, AT, role=role)
    anchor = SourceAnchor(source.id, 1, 0, len(text), text)
    entity = EntityRecord(
        "entity",
        SCOPE,
        kind,
        text,
        AT,
        (anchor,),
        labels=labels or {},
        origin="assistant_claim" if kind == "note" else "user",
    )
    return SupplementSnapshot(SCOPE, (entity,), sources=(source,))


def prediction(area="career"):
    return Prediction(area, 0.85 if area else 0.2, {"career": 3.0}, "synthetic_frozen_prediction")


def plan(snapshot, area="career", operation="batch"):
    proposal = build_review_proposal(snapshot, {"entity": prediction(area)}, scope=SCOPE, operation_id=operation)
    approval = ReviewApproval(SCOPE, proposal.fingerprint)
    return plan_review_labels(snapshot, proposal, scope=SCOPE, approval=approval), approval


@pytest.mark.parametrize("kind", ["message", "fact", "note", "case", "draw", "legacy_archive"])
@pytest.mark.parametrize("area", sorted(AREA_IDS))
@pytest.mark.parametrize("before", [{}, {"topic_id": None}, {"space_id": "daily", "topic_id": "old-topic"}])
def test_cross_entity_label_only_preview_replay_and_inverse_preserve_all_original_fields(kind, area, before):
    snapshot = fixture(kind, labels=before)
    change, approval = plan(snapshot, area)
    projected = project_plan(snapshot, change, scope=SCOPE, approval=approval)
    assert projected.entities[0].labels["space_id"] == area
    assert projected.entities[0].text == snapshot.entities[0].text
    assert projected.entities[0].anchors == snapshot.entities[0].anchors
    assert projected.entities[0].said_at == snapshot.entities[0].said_at
    assert projected.sources == snapshot.sources
    assert all(
        op.field in {"space_id", "topic_id", "space_secondary", "route_source", "route_confidence"} for op in change.ops
    )
    assert project_plan(projected, change, scope=SCOPE, approval=approval) == projected
    restored = project_undo(projected, change, scope=SCOPE)
    assert restored.entities == snapshot.entities and restored.sources == snapshot.sources
    assert project_undo(restored, change, scope=SCOPE) == restored
    with pytest.raises(SupplementConflict):
        project_plan(restored, change, scope=SCOPE, approval=approval)


@pytest.mark.parametrize("kind", ["message", "fact", "note", "case", "draw", "legacy_archive"])
def test_abstention_stays_in_waiting_tray_without_a_synthetic_daily_assignment(kind):
    snapshot = fixture(kind)
    proposal = build_review_proposal(snapshot, {"entity": prediction(None)}, scope=SCOPE, operation_id="waiting")
    view = review_data(proposal, snapshot, scope=SCOPE)
    assert len(view["waiting"]) == 1 and not any(area["items"] for area in view["areas"])
    change = plan_review_labels(snapshot, proposal, scope=SCOPE, approval=ReviewApproval(SCOPE, proposal.fingerprint))
    assert not change.ops
    projected = project_plan(snapshot, change, scope=SCOPE, approval=ReviewApproval(SCOPE, proposal.fingerprint))
    assert projected.entities == snapshot.entities
    revoked = replace(snapshot, sources=(replace(snapshot.sources[0], revoked=True),))
    with pytest.raises(ValueError):
        review_data(proposal, revoked, scope=SCOPE)
    with pytest.raises(ValueError):
        project_plan(revoked, change, scope=SCOPE, approval=ReviewApproval(SCOPE, proposal.fingerprint))


@pytest.mark.parametrize("text", ["我确诊失眠", "我的房贷80万元", "我妈妈确诊疾病"])
def test_sensitive_labels_need_one_source_bound_confirmation_in_addition_to_review(text):
    snapshot = fixture(text=text)
    proposal = build_review_proposal(snapshot, {"entity": prediction()}, scope=SCOPE, operation_id="sensitive")
    entry = proposal.entries[0]
    approval = ReviewApproval(SCOPE, proposal.fingerprint)
    with pytest.raises(SupplementConflict, match="sensitive_confirmation_required"):
        plan_review_labels(snapshot, proposal, scope=SCOPE, approval=approval)
    grant = SensitiveGrant(SCOPE, "entity", 1, entry.evidence_fingerprint, entry.sensitive_categories)
    change = plan_review_labels(snapshot, proposal, scope=SCOPE, approval=approval, sensitive_grants=(grant,))
    assert project_plan(snapshot, change, scope=SCOPE, approval=approval).entities[0].labels["space_id"] == "career"
    for bad in (
        replace(grant, decision="declined"),
        replace(grant, entity_revision=2),
        replace(grant, evidence_fingerprint="wrong"),
        replace(grant, scope=MemoryScope("other", "self")),
    ):
        with pytest.raises(SupplementConflict):
            plan_review_labels(snapshot, proposal, scope=SCOPE, approval=approval, sensitive_grants=(bad,))


@pytest.mark.parametrize("field,value", [("active", False), ("current", False), ("revoked", True), ("incognito", True)])
def test_entity_lifecycle_flags_are_rechecked_at_planning_and_projection(field, value):
    snapshot = fixture()
    change, approval = plan(snapshot)
    changed = replace(snapshot, entities=(replace(snapshot.entities[0], **{field: value}),))
    with pytest.raises(ValueError):
        build_review_proposal(changed, {"entity": prediction()}, scope=SCOPE, operation_id="bad")
    with pytest.raises(ValueError):
        project_plan(changed, change, scope=SCOPE, approval=approval)


@pytest.mark.parametrize(
    "field,value",
    [
        ("active", False),
        ("revoked", True),
        ("incognito", True),
        ("optout", True),
        ("revision", 2),
        ("role", "assistant"),
        ("owner_id", "other"),
    ],
)
def test_source_revocation_revision_and_owner_cannot_be_resurrected_by_replay_or_undo(field, value):
    snapshot = fixture()
    change, approval = plan(snapshot)
    applied = project_plan(snapshot, change, scope=SCOPE, approval=approval)
    source = replace(snapshot.sources[0], **{field: value})
    for target in (snapshot, applied):
        bad = replace(target, sources=(source,))
        with pytest.raises(ValueError):
            project_plan(bad, change, scope=SCOPE, approval=approval)
    with pytest.raises(ValueError):
        project_undo(replace(applied, sources=(source,)), change, scope=SCOPE)


def test_review_fingerprint_tampering_decline_scope_and_snapshot_staleness_fail_closed():
    snapshot = fixture()
    proposal = build_review_proposal(snapshot, {"entity": prediction()}, scope=SCOPE, operation_id="review")
    good = ReviewApproval(SCOPE, proposal.fingerprint)
    for approval in (
        replace(good, decision="declined"),
        replace(good, fingerprint="wrong"),
        replace(good, scope=MemoryScope("other", "self")),
    ):
        with pytest.raises(ValueError):
            plan_review_labels(snapshot, proposal, scope=SCOPE, approval=approval)
    for bad in (replace(proposal, fingerprint="wrong"), replace(proposal, operation_id="other")):
        with pytest.raises(ValueError):
            plan_review_labels(snapshot, bad, scope=SCOPE, approval=good)
    for bad in (
        replace(snapshot, revision=1),
        replace(snapshot, source_epoch=1),
        replace(snapshot, entities=(replace(snapshot.entities[0], revision=2),)),
    ):
        with pytest.raises(ValueError):
            plan_review_labels(bad, proposal, scope=SCOPE, approval=good)


def test_resealing_a_changed_target_does_not_reuse_an_approval_for_a_different_reviewed_assignment():
    snapshot = fixture()
    change, approval = plan(snapshot)
    altered = tuple(
        replace(op, after=FieldValue(True, '"finance"')) if op.field == "space_id" else op for op in change.ops
    )
    resealed = seal_plan(replace(change, ops=altered))
    with pytest.raises(SupplementConflict, match="plan_differs_from_reviewed_proposal"):
        project_plan(snapshot, resealed, scope=SCOPE, approval=approval)


@pytest.mark.parametrize("text", ["密码：synthetic-not-real", "我的身份证号码未展示"])
def test_secret_sources_never_reach_a_review_sample_or_label_plan(text):
    snapshot = fixture(text=text)
    with pytest.raises(ValueError):
        build_review_proposal(snapshot, {"entity": prediction()}, scope=SCOPE, operation_id="secret")


def topic_fixture(age=timedelta(days=14), status="open"):
    snapshot = fixture(text="我想讨论近期安排")
    topic = TopicRecord("topic", SCOPE, AT, snapshot.entities[0].anchors, status=status, title="合成话题")
    return replace(snapshot, topics=(topic,)), FrozenClock(AT + age)


@pytest.mark.parametrize(
    "age,eligible",
    [
        (timedelta(days=14) - timedelta(microseconds=1), False),
        (timedelta(days=14), True),
        (timedelta(days=14, seconds=1), True),
    ],
)
def test_fourteen_day_archive_boundary_is_aware_elapsed_time_and_reversible(age, eligible):
    snapshot, clock = topic_fixture(age)
    proposal = plan_topic_archive(snapshot, scope=SCOPE, clock=clock, operation_id="archive")
    assert bool(proposal.entries) == eligible
    approval = ReviewApproval(SCOPE, proposal.fingerprint)
    change = plan_archive_review(snapshot, proposal, scope=SCOPE, approval=approval)
    applied = project_plan(snapshot, change, scope=SCOPE, approval=approval)
    assert applied.topics[0].status == ("archived" if eligible else "open")
    assert project_undo(applied, change, scope=SCOPE).topics == snapshot.topics


@pytest.mark.parametrize("status", ["case", "archived"])
def test_background_archive_does_not_close_cases_or_rearchive_old_topics(status):
    snapshot, clock = topic_fixture(timedelta(days=30), status)
    assert not plan_topic_archive(snapshot, scope=SCOPE, clock=clock, operation_id="no-close").entries


def test_archive_review_is_invalidated_by_a_new_topic_message_even_if_id_is_unchanged():
    snapshot, clock = topic_fixture()
    proposal = plan_topic_archive(snapshot, scope=SCOPE, clock=clock, operation_id="archive")
    changed = replace(snapshot, topics=(replace(snapshot.topics[0], last_at=clock.now(), revision=2),))
    with pytest.raises(ValueError):
        plan_archive_review(changed, proposal, scope=SCOPE, approval=ReviewApproval(SCOPE, proposal.fingerprint))


def test_explicit_goal_upgrade_is_an_intent_without_case_migration_or_any_snapshot_mutation():
    snapshot, clock = topic_fixture()
    text = "我的目标是三个月内拿到合适的工作"
    source = MemorySource("goal", SCOPE.owner_id, SCOPE.subject_id, text, clock.now())
    snapshot = replace(snapshot, sources=(*snapshot.sources, source))
    anchor = SourceAnchor("goal", 1, 0, len(text), text)
    intent = propose_case_upgrade(snapshot, "topic", anchor, scope=SCOPE, clock=clock, operation_id="goal")
    assert intent.strategy == "undecided" and intent.requires_review and intent.action == "upgrade_case"
    assert intent.goal_anchor == anchor and intent.goal == text and snapshot.topics[0].status == "open"
    with pytest.raises(ValueError):
        propose_case_upgrade(
            snapshot, "topic", replace(anchor, revision=2), scope=SCOPE, clock=clock, operation_id="bad"
        )


@pytest.mark.parametrize(
    "text",
    [
        "我不想要拿到这个资格。",
        "我并非希望完成这个目标",
        "我没有这个目标",
        "我放弃拿到那个资格",
        "If my goal is an interview tomorrow.",
        "Suppose my goal is learning.",
        "My goal is not my goal.",
        "I do not want to achieve that goal.",
        "Perhaps my goal is attending a course.",
    ],
)
def test_negated_and_conditional_goals_do_not_authorize_case_upgrade(text):
    snapshot, clock = topic_fixture()
    source = MemorySource("goal", SCOPE.owner_id, SCOPE.subject_id, text, clock.now())
    snapshot = replace(snapshot, sources=(*snapshot.sources, source))
    anchor = SourceAnchor("goal", 1, 0, len(text), text)
    with pytest.raises(ValueError):
        propose_case_upgrade(snapshot, "topic", anchor, scope=SCOPE, clock=clock, operation_id="nonasserted")


def test_model_entity_secret_text_is_blocked_even_with_a_benign_original_anchor():
    snapshot = fixture()
    entity = replace(snapshot.entities[0], text="模型摘要写着密码：synthetic-only")
    with pytest.raises(SupplementConflict, match="secret_entity_forbidden"):
        build_review_proposal(
            replace(snapshot, entities=(entity,)), {entity.id: prediction()}, scope=SCOPE, operation_id="secret"
        )


@pytest.mark.parametrize(
    "offset,current", [(timedelta(days=1), True), (timedelta(), False), (timedelta(days=-1), False)]
)
def test_memory_fact_adapter_distinguishes_future_expiry_from_expired_facts_with_explicit_clock(offset, current):
    snapshot = fixture()
    entity = snapshot.entities[0]
    fact = MemoryFact(
        "fact",
        SCOPE.owner_id,
        SCOPE.subject_id,
        "event",
        entity.text,
        ("entity",),
        AT,
        AT,
        anchors=entity.anchors,
        valid_to=AT + timedelta(days=2),
    )
    memory = MemorySnapshot(SCOPE, facts=(fact,), sources=snapshot.sources)
    with pytest.raises(SupplementConflict, match="fact_validity_clock_required"):
        entity_from_fact(fact, memory)
    projected = entity_from_fact(fact, memory, clock=FrozenClock(fact.valid_to - offset))
    assert projected.current is current


def test_legacy_message_bridge_produces_only_old_compatible_label_changes_and_full_inverse():
    snapshot = fixture("message")
    change, approval = plan(snapshot)
    entity, source = snapshot.entities[0], snapshot.sources[0]
    document = {
        "owner_id": SCOPE.owner_id,
        "subject_id": SCOPE.subject_id,
        "topics": {},
        "messages": {
            entity.id: {
                "id": entity.id,
                "owner_id": SCOPE.owner_id,
                "subject_id": SCOPE.subject_id,
                "content": source.text,
                "role": "user",
                "at_ms": int(source.at.timestamp() * 1000),
                "revision": 1,
            },
        },
    }
    changeset = to_legacy_changeset(snapshot, change, document, scope=SCOPE, approval=approval)
    store = MemoryChangeStore(document)
    assert store.apply(changeset)["messages"][entity.id]["space_id"] == "career"
    assert store.revert(changeset.batch_id) == document
    nonmessage = fixture("fact")
    nonplan, consent = plan(nonmessage)
    with pytest.raises(SupplementConflict, match="mainline_entity_adapter_required"):
        to_legacy_changeset(nonmessage, nonplan, document, scope=SCOPE, approval=consent)


@pytest.mark.parametrize("seed", range(300))
def test_random_label_field_presence_and_values_survive_preview_then_inverse(seed):
    rng = random.Random(seed)
    before = {
        key: value
        for key, value in (("space_id", "daily"), ("topic_id", None), ("space_secondary", "family"))
        if rng.choice((True, False))
    }
    snapshot = fixture(rng.choice(("fact", "note", "case", "draw", "legacy_archive")), labels=before)
    change, approval = plan(snapshot, rng.choice(tuple(sorted(AREA_IDS))), f"random-{seed}")
    restored = project_undo(project_plan(snapshot, change, scope=SCOPE, approval=approval), change, scope=SCOPE)
    assert restored.entities == snapshot.entities and restored.sources == snapshot.sources
    assert evidence_fingerprint(restored.entities[0]) == evidence_fingerprint(snapshot.entities[0])

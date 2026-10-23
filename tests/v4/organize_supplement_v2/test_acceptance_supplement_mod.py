"""Independent review/undo/source boundaries; no classification tuning or real-history access."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.organize.supplement_v2 import (
    EntityRecord,
    ReviewApproval,
    SensitiveGrant,
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
)
from mingjing_core.organize.v2.contracts import Prediction
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = MemoryScope("synthetic-supplement-owner", "self")
PREDICTION = Prediction("career", 0.9, {"career": 3}, "synthetic-candidate")


def fixture(*, kind="fact", text="我参加合成读书会。", labels=None):
    source = MemorySource("synthetic-entity", SCOPE.owner_id, SCOPE.subject_id, text, AT - timedelta(days=30))
    anchor = SourceAnchor(source.id, source.revision, 0, len(text), text)
    entity = EntityRecord(source.id, SCOPE, kind, text, source.at, (anchor,), labels=labels or {})
    return SupplementSnapshot(SCOPE, entities=(entity,), sources=(source,))


def reviewed(snapshot, prediction=PREDICTION, *, grants=()):
    proposal = build_review_proposal(
        snapshot, {snapshot.entities[0].id: prediction}, scope=SCOPE, operation_id="review-1"
    )
    approval = ReviewApproval(SCOPE, proposal.fingerprint)
    plan = plan_review_labels(snapshot, proposal, scope=SCOPE, approval=approval, sensitive_grants=grants)
    return proposal, approval, plan


@pytest.mark.parametrize("kind", ["message", "fact", "note", "case", "draw", "legacy_archive"])
@pytest.mark.parametrize("labels", [{}, {"space_secondary": None}, {"space_id": "daily", "topic_id": "old-topic"}])
def test_review_copy_apply_replay_undo_restores_all_entity_fields(kind, labels):
    snapshot = fixture(kind=kind, labels=labels)
    _, approval, plan = reviewed(snapshot)
    applied = project_plan(snapshot, plan, scope=SCOPE, approval=approval)
    assert applied.entities[0].labels["space_id"] == "career"
    assert applied.entities[0].text == snapshot.entities[0].text
    assert applied.entities[0].anchors == snapshot.entities[0].anchors
    assert project_plan(applied, plan, scope=SCOPE, approval=approval) == applied
    restored = project_undo(applied, plan, scope=SCOPE)
    assert restored.entities == snapshot.entities and restored.sources == snapshot.sources
    assert project_undo(restored, plan, scope=SCOPE) == restored
    assert snapshot.entities[0].labels == labels


def test_abstention_is_visible_review_tray_and_never_daily_assignment():
    snapshot = fixture()
    waiting = Prediction(None, 0.2, {}, "insufficient_evidence")
    proposal, approval, plan = reviewed(snapshot, waiting)
    payload = review_data(proposal, snapshot, scope=SCOPE)
    assert len(payload["waiting"]) == 1
    assert not any(area["items"] for area in payload["areas"])
    assert plan.ops == ()
    assert project_plan(snapshot, plan, scope=SCOPE, approval=approval).entities == snapshot.entities


@pytest.mark.parametrize(
    "change",
    [
        {"revoked": True},
        {"active": False},
        {"incognito": True},
        {"optout": True},
        {"revision": 2},
        {"role": "assistant"},
        {"owner_id": "other"},
        {"subject_id": "other"},
    ],
)
def test_source_recheck_blocks_plan_replay_and_undo_after_withdrawal(change):
    snapshot = fixture()
    proposal, approval, plan = reviewed(snapshot)
    applied = project_plan(snapshot, plan, scope=SCOPE, approval=approval)
    withdrawn = replace(snapshot.sources[0], **change)
    for function, state in ((project_plan, snapshot), (project_plan, applied)):
        with pytest.raises(ValueError):
            function(replace(state, sources=(withdrawn,)), plan, scope=SCOPE, approval=approval)
    with pytest.raises(ValueError):
        project_undo(replace(applied, sources=(withdrawn,)), plan, scope=SCOPE)
    with pytest.raises(ValueError):
        review_data(proposal, replace(snapshot, sources=(withdrawn,)), scope=SCOPE)


def test_changed_epoch_revision_or_field_never_undoes_newer_user_edit():
    snapshot = fixture()
    _, approval, plan = reviewed(snapshot)
    applied = project_plan(snapshot, plan, scope=SCOPE, approval=approval)
    states = [
        replace(applied, source_epoch=1),
        replace(applied, revision=applied.revision + 1),
        replace(applied, entities=(replace(applied.entities[0], labels={"space_id": "family"}),)),
    ]
    for current in states:
        with pytest.raises(ValueError):
            project_undo(current, plan, scope=SCOPE)


def test_sensitive_confirmation_binds_original_entity_revision_and_evidence():
    snapshot = fixture(text="我最近有些失眠。")
    entity = snapshot.entities[0]
    with pytest.raises(ValueError, match="sensitive_confirmation_required"):
        reviewed(snapshot)
    grant = SensitiveGrant(SCOPE, entity.id, entity.revision, evidence_fingerprint(entity), ("health",))
    _, approval, plan = reviewed(snapshot, grants=(grant,))
    assert project_plan(snapshot, plan, scope=SCOPE, approval=approval).entities[0].labels["space_id"] == "career"
    for bad in (
        replace(grant, entity_revision=2),
        replace(grant, evidence_fingerprint="wrong"),
        replace(grant, decision="declined"),
        replace(grant, scope=MemoryScope("other", "self")),
    ):
        with pytest.raises(ValueError):
            reviewed(snapshot, grants=(bad,))


def test_secret_in_model_entity_summary_has_no_review_sample_and_cannot_apply():
    snapshot = fixture()
    entity = replace(snapshot.entities[0], text="模型错误拼入密码条目synthetic-placeholder")
    snapshot = replace(snapshot, entities=(entity,))
    with pytest.raises(ValueError, match="secret_entity_forbidden") as error:
        build_review_proposal(snapshot, {entity.id: PREDICTION}, scope=SCOPE, operation_id="secret-review")
    assert "synthetic-placeholder" not in str(error.value) and "密码条目" not in str(error.value)


@pytest.mark.parametrize("offset,eligible", [(-1, False), (0, True), (1, True)])
def test_topic_fourteen_day_boundary_archives_only_open_topics(offset, eligible):
    snapshot = fixture()
    topic = TopicRecord(
        "synthetic-topic",
        SCOPE,
        AT - timedelta(days=14, seconds=offset),
        snapshot.entities[0].anchors,
        title="合成话题",
    )
    snapshot = replace(snapshot, topics=(topic,))
    proposal = plan_topic_archive(snapshot, scope=SCOPE, clock=FrozenClock(AT), operation_id="archive-1")
    assert bool(proposal.entries) is eligible
    if eligible:
        approval = ReviewApproval(SCOPE, proposal.fingerprint)
        plan = plan_archive_review(snapshot, proposal, scope=SCOPE, approval=approval)
        applied = project_plan(snapshot, plan, scope=SCOPE, approval=approval)
        assert applied.topics[0].status == "archived"
        assert project_undo(applied, plan, scope=SCOPE).topics == snapshot.topics


def test_new_message_invalidates_archive_proposal_and_case_is_not_auto_closed():
    snapshot = fixture()
    topic = TopicRecord("synthetic-topic", SCOPE, AT - timedelta(days=14), snapshot.entities[0].anchors)
    snapshot = replace(snapshot, topics=(topic,))
    proposal = plan_topic_archive(snapshot, scope=SCOPE, clock=FrozenClock(AT), operation_id="archive-1")
    fresh = replace(snapshot, topics=(replace(topic, last_at=AT, revision=2),))
    with pytest.raises(ValueError):
        plan_archive_review(fresh, proposal, scope=SCOPE, approval=ReviewApproval(SCOPE, proposal.fingerprint))
    case = replace(snapshot, topics=(replace(topic, status="case"),))
    assert plan_topic_archive(case, scope=SCOPE, clock=FrozenClock(AT), operation_id="archive-case").entries == ()


def test_future_expiry_fact_remains_current_but_expired_fact_cannot_be_routed():
    snapshot = fixture()
    entity = snapshot.entities[0]
    fact = MemoryFact(
        entity.id,
        SCOPE.owner_id,
        SCOPE.subject_id,
        "background",
        entity.text,
        (snapshot.sources[0].id,),
        entity.said_at,
        entity.said_at,
        anchors=entity.anchors,
        valid_to=AT + timedelta(days=1),
    )
    memory = MemorySnapshot(SCOPE, (fact,), snapshot.sources)
    assert entity_from_fact(fact, memory, clock=FrozenClock(AT)).current
    expired = replace(fact, valid_to=AT - timedelta(seconds=1))
    assert not entity_from_fact(expired, replace(memory, facts=(expired,)), clock=FrozenClock(AT)).current


@pytest.mark.parametrize(
    "goal", ["我不想要拿到这个资格。", "假如我想要完成它。", "If my goal is an interview tomorrow."]
)
def test_negated_or_conditional_goal_does_not_generate_case_upgrade_intent(goal):
    snapshot = fixture(text=goal)
    topic = TopicRecord("synthetic-topic", SCOPE, snapshot.sources[0].at, snapshot.entities[0].anchors)
    snapshot = replace(snapshot, topics=(topic,))
    with pytest.raises(ValueError):
        propose_case_upgrade(
            snapshot,
            topic.id,
            snapshot.entities[0].anchors[0],
            scope=SCOPE,
            clock=FrozenClock(AT),
            operation_id="upgrade-negative",
        )

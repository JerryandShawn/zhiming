"""Actual offline business modules compose without treating copied source proofs as real DB authority."""

import hashlib
import random
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.briefing_v2 import (
    BasisRef,
    BriefItem,
    BriefSourceState,
    calendar_snapshot,
    compose_briefing,
    subscription_basis,
)
from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.memory.retrieval_types import SearchSource, SearchUnit, SourceRef
from mingjing_core.memory2.archive import plan_archives
from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.memory2.event_time_extended_v2 import absolute_event_candidate_extended
from mingjing_core.memory2.mutations import apply_plan, plan_write
from mingjing_core.memory2.undo import undo_plan
from mingjing_core.organize.partition_context_v2 import project_partition_context
from mingjing_core.organize.partition_context_v2_contracts import PartitionRecord, PartitionScope
from mingjing_core.organize.supplement_v2 import (
    ReviewApproval,
    SupplementSnapshot,
    build_review_proposal,
    entity_from_fact,
    plan_review_labels,
    project_plan,
    project_undo,
)
from mingjing_core.organize.v2.contracts import Prediction
from mingjing_core.scheduling.brief_schedule import BriefSubscription
from mingjing_core.scheduling.delivery_contracts import DeliveryRequest
from mingjing_core.timekit.clock import FrozenClock

ZONES = ("Asia/Shanghai", "Asia/Tokyo", "UTC", "America/New_York", "Europe/London", "Pacific/Auckland")


def saved_event(index, zone):
    now = datetime(2026, 10, 21, 7, tzinfo=ZoneInfo(zone))
    clock, scope = FrozenClock(now + timedelta(seconds=1)), MemoryScope(f"synthetic-day-owner-{index}", "self")
    raw = "请提醒我：明天下午三点参加合成读书会。"
    source = MemorySource(f"raw-{index}", scope.owner_id, scope.subject_id, raw, now)
    anchor = SourceAnchor(source.id, source.revision, 0, len(raw), raw)
    original = MemoryFact(
        f"event-{index}",
        scope.owner_id,
        scope.subject_id,
        "event",
        raw,
        (source.id,),
        now,
        clock.now(),
        anchors=(anchor,),
    )
    snapshot = MemorySnapshot(scope, sources=(source,))
    projected = absolute_event_candidate_extended(original, snapshot, tz=zone)
    assert projected.projected is not None and projected.original == original
    plan = plan_write(snapshot, projected.projected, scope=scope, operation_id=f"write-{index}", clock=clock)
    stored = apply_plan(snapshot, plan, clock=clock).snapshot
    assert stored.sources[0].text == raw and stored.facts[0].anchors == original.anchors
    return stored, clock


def reviewed_route(memory, clock, index):
    entity = entity_from_fact(memory.facts[0], memory, clock=clock)
    snapshot = SupplementSnapshot(memory.scope, entities=(entity,), sources=memory.sources)
    prediction = Prediction("career", 0.9, {"career": 3}, "synthetic-human-reviewed")
    proposal = build_review_proposal(
        snapshot, {entity.id: prediction}, scope=memory.scope, operation_id=f"label-{index}"
    )
    approval = ReviewApproval(memory.scope, proposal.fingerprint)
    plan = plan_review_labels(snapshot, proposal, scope=memory.scope, approval=approval)
    applied = project_plan(snapshot, plan, scope=memory.scope, approval=approval)
    restored = project_undo(applied, plan, scope=memory.scope)
    assert restored.entities == snapshot.entities and restored.sources == snapshot.sources
    assert applied.entities[0].text == memory.facts[0].text and applied.entities[0].labels["space_id"] == "career"
    return applied.entities[0]


def partition(fact, entity, source, clock):
    scope = PartitionScope(fact.owner_id, fact.subject_id, "life:self", "career", "reading")
    unit = SearchUnit(
        fact.id,
        fact.owner_id,
        fact.subject_id,
        "event",
        fact.text,
        fact.said_at,
        event_at=fact.event_at,
        source_refs=(SourceRef(source.id, source.revision),),
        valid=fact.status == "active",
    )
    record = PartitionRecord(unit, scope.life_thread_id, entity.labels["space_id"], "retrieval", score=0.4)
    current = SearchSource(
        source.id,
        source.owner_id,
        source.subject_id,
        source.revision,
        active=source.active and not source.optout,
        redacted=source.revoked,
        incognito=source.incognito,
        role=source.role,
        origin=source.origin,
    )
    return project_partition_context((record,), (current,), scope=scope, source_epoch=0, clock=clock)


def brief(fact, entity, source, clock, zone):
    scope = FollowupScope(fact.owner_id, fact.subject_id)
    subscription = BriefSubscription(scope, time_zone=zone)
    binding = subscription_basis(subscription)
    digest = hashlib.sha256(source.text.encode()).hexdigest()
    ref = BasisRef("m1", source.id, source.revision, source.owner_id, source.subject_id, digest)
    # Candidate flags intentionally remain the preparation snapshot; current source_states must still gate it.
    candidate = FollowupCandidate(
        fact.id, fact.owner_id, fact.subject_id, "reminder", fact.event_at, explicit_requested=True, text=fact.text
    )
    item = BriefItem(
        DeliveryRequest("occurrence:" + fact.id, candidate, fact.event_at),
        (ref,),
        entity.labels["space_id"],
        (
            BriefSourceState(
                source.id,
                scope,
                source.revision,
                digest,
                active=source.active and not source.optout,
                revoked=source.revoked,
                incognito=source.incognito,
            ),
        ),
    )
    return compose_briefing(
        scope=scope,
        subscription=subscription,
        settings=FollowupSettings(timezone=zone),
        receptivity=ReceptivityState(scope.owner_id, scope.subject_id),
        clock=clock,
        calendar=calendar_snapshot(scope=scope, clock=clock, timezone=zone),
        items=(item,),
        subscription_state=BriefSourceState(binding.source_id, scope, binding.revision, binding.value_sha256),
    )


@pytest.mark.parametrize("zone", ZONES)
def test_source_to_review_to_context_to_morning_brief_and_c2_undo(zone):
    memory, clock = saved_event(1, zone)
    entity = reviewed_route(memory, clock, 1)
    fact, source = memory.facts[0], memory.sources[0]
    context = partition(fact, entity, source, clock)
    assert context.retrieval[0].weighted_score == pytest.approx(0.6)
    result = brief(fact, entity, source, clock, zone)
    assert result.delivery.disposition == "push"
    assert fact.text in next(section for section in result.sections if section.id == "area_career").lines[0].text
    later = FrozenClock(fact.event_end + timedelta(seconds=1))
    plan = plan_archives(memory, scope=memory.scope, clock=later, operation_id="archive-combined")
    archived = apply_plan(memory, plan, clock=later).snapshot
    assert archived.facts[0].status == "archived"
    assert partition(archived.facts[0], entity, source, later).retrieval == ()
    restored = undo_plan(archived, plan, operation_id="undo-archive-combined")
    assert restored.snapshot.facts == memory.facts and restored.snapshot.sources == memory.sources


def test_300_random_scope_zone_source_withdrawals_cannot_enter_context_or_any_brief_section():
    generator = random.Random(2026102103)
    for index in range(300):
        zone = generator.choice(ZONES)
        memory, clock = saved_event(index + 100, zone)
        entity = reviewed_route(memory, clock, index + 100)
        fact, source = memory.facts[0], memory.sources[0]
        change = generator.choice(({"revoked": True}, {"active": False}, {"incognito": True}, {"optout": True}))
        withdrawn = replace(source, **change)
        assert partition(fact, entity, withdrawn, clock).retrieval == ()
        result = brief(fact, entity, withdrawn, clock, zone)
        assert all(fact.text not in line.text for section in result.sections for line in section.lines)
        assert not any(ref.source_id == source.id for ref in result.basis)
        assert result.effects.model_calls == result.effects.writes == result.effects.notifications == 0

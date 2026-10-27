"""Archive plans and upgrade intents never choose the mainline's case migration strategy."""

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from mingjing_core.memory2.contracts import MemoryScope, SourceAnchor, utc
from mingjing_core.memory2.validation import require_text
from mingjing_core.organize._change_values import FieldChange, FieldValue
from mingjing_core.timekit.clock import Clock

from .contracts import EntityRecord, ReviewApproval, SupplementConflict, SupplementSnapshot
from .guards import (
    authorize_entity,
    authorize_topic,
    digest,
    entity_sensitivity,
    evidence_fingerprint,
    require_approval,
    require_scope,
    topic_fingerprint,
)
from .intent_policy import asserted_goal
from .plan_contracts import (
    RecordGuard,
    SupplementPlan,
    TopicArchiveEntry,
    TopicArchiveProposal,
    archive_fingerprint,
    seal_plan,
)


def plan_topic_archive(
    snapshot: SupplementSnapshot,
    *,
    scope: MemoryScope,
    clock: Clock,
    operation_id: str,
) -> TopicArchiveProposal:
    require_scope(snapshot, scope)
    require_text(operation_id)
    now = utc(clock.now())
    entries = []
    for topic in sorted(snapshot.topics, key=lambda item: item.id):
        authorize_topic(topic, snapshot, scope)
        if topic.last_at > now:
            raise SupplementConflict("topic_last_at_in_future")
        # An ongoing case needs a mainline/product decision, never background auto-closure.
        if topic.status == "open" and now - topic.last_at >= timedelta(days=14):
            entries.append(TopicArchiveEntry(topic.id, topic.revision, topic_fingerprint(topic)))
    proposal = TopicArchiveProposal(
        scope,
        operation_id,
        snapshot.revision,
        snapshot.source_epoch,
        now.isoformat(),
        tuple(entries),
    )
    return replace(proposal, fingerprint=archive_fingerprint(proposal))


def plan_archive_review(
    snapshot: SupplementSnapshot,
    proposal: TopicArchiveProposal,
    *,
    scope: MemoryScope,
    approval: ReviewApproval,
) -> SupplementPlan:
    require_scope(snapshot, scope)
    if not isinstance(proposal, TopicArchiveProposal) or proposal.scope != scope:
        raise SupplementConflict("archive_scope_mismatch")
    require_approval(approval, scope, proposal.fingerprint)
    if proposal.fingerprint != archive_fingerprint(proposal):
        raise SupplementConflict("archive_fingerprint_mismatch")
    if (snapshot.revision, snapshot.source_epoch) != (proposal.expected_revision, proposal.source_epoch):
        raise SupplementConflict("archive_snapshot_changed")
    changes, guards = [], []
    at = utc(datetime.fromisoformat(proposal.evaluated_at))
    for entry in proposal.entries:
        topic = snapshot.topic(entry.topic_id)
        if topic is None:
            raise SupplementConflict("topic_missing")
        authorize_topic(topic, snapshot, scope)
        if topic.revision != entry.topic_revision or topic_fingerprint(topic) != entry.evidence_fingerprint:
            raise SupplementConflict("topic_evidence_changed")
        if topic.status != "open" or at - topic.last_at < timedelta(days=14):
            raise SupplementConflict("topic_not_archive_eligible")
        changes.append(
            FieldChange("topics", topic.id, "status", FieldValue(True, '"open"'), FieldValue(True, '"archived"'))
        )
        guards.append(RecordGuard("topics", topic.id, topic.revision, topic_fingerprint(topic)))
    return seal_plan(
        SupplementPlan(
            scope,
            proposal.operation_id,
            snapshot.revision,
            snapshot.source_epoch,
            proposal.fingerprint,
            tuple(changes),
            tuple(guards),
            reviewed=proposal,
        )
    )


@dataclass(frozen=True)
class CaseUpgradeIntent:
    scope: MemoryScope
    operation_id: str
    topic_id: str
    topic_revision: int
    topic_fingerprint: str
    goal: str = field(repr=False)
    goal_anchor: SourceAnchor = field(repr=False)
    goal_fingerprint: str
    evaluated_at: datetime
    sensitive_categories: tuple[str, ...]
    fingerprint: str
    action: str = "upgrade_case"
    strategy: str = "undecided"
    requires_review: bool = True


def propose_case_upgrade(
    snapshot: SupplementSnapshot,
    topic_id: str,
    goal_anchor: SourceAnchor,
    *,
    scope: MemoryScope,
    clock: Clock,
    operation_id: str,
) -> CaseUpgradeIntent:
    require_scope(snapshot, scope)
    require_text(operation_id)
    topic = snapshot.topic(topic_id)
    if topic is None:
        raise SupplementConflict("topic_missing")
    authorize_topic(topic, snapshot, scope)
    if topic.status != "open" or not isinstance(goal_anchor, SourceAnchor):
        raise SupplementConflict("topic_not_upgrade_eligible")
    source = next((item for item in snapshot.sources if item.id == goal_anchor.source_id), None)
    if source is None:
        raise SupplementConflict("goal_source_missing")
    entity = EntityRecord("goal:" + topic.id, scope, "case", goal_anchor.quote, source.at, (goal_anchor,))
    authorize_entity(entity, snapshot, scope)
    if not asserted_goal(source.text, goal_anchor.start, goal_anchor.end):
        raise SupplementConflict("goal_not_asserted")
    now = utc(clock.now())
    if source.at > now or topic.last_at > now or len(goal_anchor.quote) > 500:
        raise SupplementConflict("goal_time_or_length_invalid")
    if not re.search(r"目标|希望|想要|拿到|完成|做到|通过|\bgoal\b|\bachieve\b", goal_anchor.quote, re.I):
        raise SupplementConflict("explicit_goal_required")
    sensitivity = entity_sensitivity(entity)
    if sensitivity.secret or sensitivity.profile_confirmation:
        raise SupplementConflict("goal_source_forbidden")
    fingerprint = digest(
        (
            scope.owner_id,
            scope.subject_id,
            operation_id,
            topic.id,
            topic.revision,
            topic_fingerprint(topic),
            evidence_fingerprint(entity),
            now.isoformat(),
        )
    )
    return CaseUpgradeIntent(
        scope,
        operation_id,
        topic.id,
        topic.revision,
        topic_fingerprint(topic),
        goal_anchor.quote,
        goal_anchor,
        evidence_fingerprint(entity),
        now,
        sensitivity.categories,
        fingerprint,
    )

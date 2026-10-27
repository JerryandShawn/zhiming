"""Sealed review plans use field-presence aware inverse operations, never database mutations."""

from dataclasses import dataclass, field, replace

from mingjing_core.memory2.contracts import MemoryScope
from mingjing_core.organize._change_values import FieldChange
from mingjing_core.organize.v2.contracts import Prediction

from .contracts import SensitiveGrant
from .guards import digest


@dataclass(frozen=True)
class ReviewEntry:
    entity_id: str
    kind: str
    entity_revision: int
    evidence_fingerprint: str
    prediction: Prediction
    sample: str = field(repr=False)
    sensitive_categories: tuple[str, ...] = ()
    secret: bool = False
    profile_confirmation: bool = False
    labels_fingerprint: str = ""


def entry_values(entry: ReviewEntry) -> tuple[object, ...]:
    prediction = entry.prediction
    return (
        entry.entity_id,
        entry.kind,
        entry.entity_revision,
        entry.evidence_fingerprint,
        prediction.area_id,
        prediction.secondary_id,
        prediction.confidence,
        dict(prediction.scores),
        prediction.reason,
        entry.sample,
        entry.sensitive_categories,
        entry.secret,
        entry.profile_confirmation,
        entry.labels_fingerprint,
    )


@dataclass(frozen=True)
class ReviewProposal:
    scope: MemoryScope
    operation_id: str
    expected_revision: int
    source_epoch: int
    entries: tuple[ReviewEntry, ...] = field(repr=False)
    fingerprint: str = ""

    @property
    def waiting(self) -> tuple[ReviewEntry, ...]:
        return tuple(entry for entry in self.entries if entry.prediction.waiting)


def proposal_fingerprint(proposal: ReviewProposal) -> str:
    return digest(
        (
            "review_labels_v2",
            proposal.scope.owner_id,
            proposal.scope.subject_id,
            proposal.operation_id,
            proposal.expected_revision,
            proposal.source_epoch,
            tuple(entry_values(entry) for entry in proposal.entries),
        )
    )


@dataclass(frozen=True)
class TopicArchiveEntry:
    topic_id: str
    topic_revision: int
    evidence_fingerprint: str


@dataclass(frozen=True)
class TopicArchiveProposal:
    scope: MemoryScope
    operation_id: str
    expected_revision: int
    source_epoch: int
    evaluated_at: str
    entries: tuple[TopicArchiveEntry, ...]
    fingerprint: str = ""


def archive_fingerprint(proposal: TopicArchiveProposal) -> str:
    return digest(
        (
            "archive_topics_v2",
            proposal.scope.owner_id,
            proposal.scope.subject_id,
            proposal.operation_id,
            proposal.expected_revision,
            proposal.source_epoch,
            proposal.evaluated_at,
            tuple((item.topic_id, item.topic_revision, item.evidence_fingerprint) for item in proposal.entries),
        )
    )


@dataclass(frozen=True)
class RecordGuard:
    collection: str
    id: str
    revision: int
    evidence_fingerprint: str


@dataclass(frozen=True)
class SupplementPlan:
    scope: MemoryScope
    operation_id: str
    expected_revision: int
    source_epoch: int
    review_fingerprint: str
    ops: tuple[FieldChange, ...] = field(repr=False)
    guards: tuple[RecordGuard, ...]
    sensitive_grants: tuple[SensitiveGrant, ...] = field(default=(), repr=False)
    fingerprint: str = ""
    reviewed: ReviewProposal | TopicArchiveProposal | None = field(default=None, repr=False)

    @property
    def inverse_ops(self) -> tuple[FieldChange, ...]:
        return tuple(op.inverse() for op in reversed(self.ops))


def plan_fingerprint(plan: SupplementPlan) -> str:
    grants = tuple(
        (
            grant.scope.owner_id,
            grant.scope.subject_id,
            grant.entity_id,
            grant.entity_revision,
            grant.evidence_fingerprint,
            grant.categories,
            grant.decision,
        )
        for grant in plan.sensitive_grants
    )
    return digest(
        (
            plan.scope.owner_id,
            plan.scope.subject_id,
            plan.operation_id,
            plan.expected_revision,
            plan.source_epoch,
            plan.review_fingerprint,
            tuple(op.as_dict() for op in plan.ops),
            tuple((item.collection, item.id, item.revision, item.evidence_fingerprint) for item in plan.guards),
            grants,
            plan.reviewed.fingerprint if isinstance(plan.reviewed, (ReviewProposal, TopicArchiveProposal)) else None,
        )
    )


def seal_plan(plan: SupplementPlan) -> SupplementPlan:
    return replace(plan, fingerprint=plan_fingerprint(plan))

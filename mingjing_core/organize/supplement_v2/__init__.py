"""Offline supplements only. ReviewApproval is a trusted host receipt, not a model-provided token."""

from .contracts import (
    EntityRecord,
    ProjectionOperation,
    ReviewApproval,
    SensitiveGrant,
    SupplementConflict,
    SupplementSnapshot,
    TopicRecord,
)
from .guards import entity_from_fact, evidence_fingerprint
from .legacy_bridge import to_legacy_changeset
from .lifecycle import CaseUpgradeIntent, plan_archive_review, plan_topic_archive, propose_case_upgrade
from .plan_contracts import ReviewEntry, ReviewProposal, SupplementPlan, TopicArchiveProposal
from .projection import project_plan, project_undo
from .review import build_review_proposal, plan_review_labels, review_data

__all__ = [
    "CaseUpgradeIntent",
    "EntityRecord",
    "ProjectionOperation",
    "ReviewApproval",
    "ReviewEntry",
    "ReviewProposal",
    "SensitiveGrant",
    "SupplementConflict",
    "SupplementPlan",
    "SupplementSnapshot",
    "TopicArchiveProposal",
    "TopicRecord",
    "build_review_proposal",
    "entity_from_fact",
    "evidence_fingerprint",
    "plan_archive_review",
    "plan_review_labels",
    "plan_topic_archive",
    "project_plan",
    "project_undo",
    "propose_case_upgrade",
    "review_data",
    "to_legacy_changeset",
]

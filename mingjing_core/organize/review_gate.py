"""Bind an additive label plan to an explicit review receipt. Never persist or approve for a user."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from mingjing_core.timekit.clock import Clock

from ._change_values import ChangeConflict, digest
from .changes import ChangeSet
from .proposal import Proposal


def _instant(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ChangeConflict("review receipt requires an aware instant")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ReviewPreview:
    batch_id: str
    owner_id: str
    subject_id: str
    fingerprint: str
    summary: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class ReviewApproval:
    """Trusted host projection of the authenticated user's approval, not proof of authentication."""

    receipt_id: str
    batch_id: str
    owner_id: str
    subject_id: str
    fingerprint: str
    reviewed_at: datetime
    accepted: bool

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.receipt_id,
                self.batch_id,
                self.owner_id,
                self.subject_id,
                self.fingerprint,
            )
        ):
            raise ChangeConflict("review receipt identity invalid")
        if type(self.accepted) is not bool:
            raise ChangeConflict("review receipt acceptance must be explicit")
        object.__setattr__(self, "reviewed_at", _instant(self.reviewed_at))


def _additive_plan(
    proposal: Proposal, document: dict[str, Any], batch_id: str
) -> ChangeSet:
    plan = proposal.to_changeset(document, batch_id)
    for op in plan.ops:
        if (
            op.collection == "messages"
            and op.before.present
            and op.before.value is not None
        ):
            raise ChangeConflict(
                "historical organization cannot overwrite existing labels"
            )
    return plan


def preview_organization(
    proposal: Proposal, document: dict[str, Any], *, batch_id: str
) -> ReviewPreview:
    plan = _additive_plan(proposal, document, batch_id)
    return ReviewPreview(
        batch_id,
        plan.owner_id,
        plan.subject_id,
        digest(plan.as_dict()),
        proposal.summary(),
    )


def approved_changeset(
    proposal: Proposal,
    document: dict[str, Any],
    approval: ReviewApproval,
    *,
    clock: Clock,
) -> ChangeSet:
    """Recompute current plan after review. Caller must verify receipt provenance in its transaction."""
    if not isinstance(approval, ReviewApproval) or not approval.accepted:
        raise ChangeConflict("explicit user review approval required")
    if (proposal.owner_id, proposal.subject_id) != (
        approval.owner_id,
        approval.subject_id,
    ):
        raise ChangeConflict("review receipt scope mismatch")
    elapsed = _instant(clock.now()) - approval.reviewed_at
    if not timedelta(0) <= elapsed <= timedelta(hours=24):
        raise ChangeConflict("review receipt expired or future dated")
    plan = _additive_plan(proposal, document, approval.batch_id)
    if digest(plan.as_dict()) != approval.fingerprint:
        raise ChangeConflict("reviewed plan changed; review again")
    return plan

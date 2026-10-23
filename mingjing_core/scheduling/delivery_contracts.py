"""Immutable delivery occurrence identity; retry timing is separate from its original due instant."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Literal

from mingjing_core.application.followups_contracts import FollowupCandidate, FollowupScope, aware

Disposition = Literal["push", "app_inbox", "deferred", "not_due", "blocked"]
LIVE_FLAGS = frozenset({"active", "source_active", "source_revoked"})


@dataclass(frozen=True)
class DeliveryRequest:
    occurrence_id: str
    candidate: FollowupCandidate = field(repr=False)
    original_due: datetime
    brief_subscribed: bool = False
    not_before: datetime | None = None

    def __post_init__(self) -> None:
        if type(self.occurrence_id) is not str or not self.occurrence_id.strip() or len(self.occurrence_id) > 250:
            raise ValueError("delivery_occurrence_required")
        if not isinstance(self.candidate, FollowupCandidate):
            raise ValueError("delivery_candidate_required")
        object.__setattr__(self, "original_due", aware(self.original_due))
        if self.candidate.due_at != self.original_due:
            raise ValueError("delivery_original_due_cannot_change")
        if type(self.brief_subscribed) is not bool:
            raise ValueError("delivery_subscription_boolean_required")
        if self.brief_subscribed and self.candidate.kind != "brief":
            raise ValueError("delivery_brief_subscription_kind_invalid")
        if self.not_before is not None:
            object.__setattr__(self, "not_before", aware(self.not_before))
            if self.not_before < self.original_due:
                raise ValueError("delivery_retry_before_original_due")


@dataclass(frozen=True)
class DeliveryPlan:
    scope: FollowupScope
    occurrence_id: str
    candidate_id: str
    kind: str
    original_due: datetime
    evaluated_at: datetime
    disposition: Disposition
    reason: str
    daily_cap: int
    preview: str = field(repr=False)
    request_key: str
    next_attempt_at: datetime | None = None
    late_seconds: float = 0
    late_minutes: int = 0
    late_note: str = ""

    @property
    def allowed(self) -> bool:
        return self.disposition == "push"

    @property
    def app_inbox_only(self) -> bool:
        return self.disposition == "app_inbox"

    @property
    def next_due(self) -> datetime | None:
        return self.next_attempt_at


def request_key(request: DeliveryRequest, scope: FollowupScope) -> str:
    candidate = request.candidate
    scope.require(candidate.owner_id, candidate.subject_id)
    values = [
        (item.name, value.isoformat() if isinstance(value := getattr(candidate, item.name), datetime) else value)
        for item in fields(FollowupCandidate)
        if item.name not in LIVE_FLAGS
    ]
    identity = [scope.owner_id, scope.subject_id, request.occurrence_id, request.original_due.isoformat(), values]
    raw = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
    return "delivery:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

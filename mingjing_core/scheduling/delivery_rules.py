"""K1/K2 plans adapt the previous delivery rules without bypassing their privacy or consent gates."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime

from mingjing_core.application.followups_contracts import (
    DeliveryDecision,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
    aware,
)
from mingjing_core.application.followups_rules import decide_delivery
from mingjing_core.timekit.clock import Clock, FrozenClock

from .delivery_contracts import DeliveryPlan, DeliveryRequest, Disposition, request_key

TIMING_REASONS = frozenset({"quiet_hours", "not_due", "adaptation_pause", "daily_cap"})


def _legacy(
    request: DeliveryRequest,
    settings: FollowupSettings,
    state: ReceptivityState,
    *,
    scope: FollowupScope,
    now: datetime,
    sent_today: int,
) -> DeliveryDecision:
    candidate = request.candidate
    if candidate.kind == "reminder":
        seconds_late = max(0, (now - request.original_due).total_seconds())
        candidate = replace(candidate, explicit_quiet_time=candidate.explicit_requested and seconds_late <= 3600)
        # K2 defaults to exactly 08:00; a longer user-selected quiet window remains authoritative.
        settings = replace(settings, resume_at=settings.quiet_end)
    return decide_delivery(candidate, settings, state, scope=scope, clock=FrozenClock(now), sent_today=sent_today)


def _result(
    request: DeliveryRequest,
    scope: FollowupScope,
    now: datetime,
    base: DeliveryDecision,
    disposition: Disposition,
    reason: str,
    next_attempt: datetime | None = None,
) -> DeliveryPlan:
    late_seconds = max(0.0, (now - request.original_due).total_seconds())
    late_minutes = math.ceil(late_seconds / 60)
    late_note = (
        f"晚了 {late_minutes} 分钟"
        if disposition == "push" and late_seconds > 0 and request.candidate.kind == "reminder"
        else ""
    )
    return DeliveryPlan(
        scope,
        request.occurrence_id,
        request.candidate.id,
        request.candidate.kind,
        request.original_due,
        now,
        disposition,
        reason,
        base.daily_cap,
        base.preview,
        request_key(request, scope),
        next_attempt,
        late_seconds,
        late_minutes,
        late_note,
    )


def plan_delivery(
    request: DeliveryRequest,
    settings: FollowupSettings,
    state: ReceptivityState,
    *,
    scope: FollowupScope,
    clock: Clock,
    sent_today: int = 0,
) -> DeliveryPlan:
    if not isinstance(request, DeliveryRequest) or not isinstance(scope, FollowupScope):
        raise ValueError("delivery_request_and_scope_required")
    now = aware(clock.now())
    base = _legacy(request, settings, state, scope=scope, now=now, sent_today=sent_today)
    if not base.allowed and base.reason not in TIMING_REASONS:
        return _result(request, scope, now, base, "blocked", base.reason)
    if request.candidate.kind == "brief" and not request.brief_subscribed:
        return _result(request, scope, now, base, "blocked", "brief_not_subscribed")
    explicit = request.candidate.kind == "reminder" and request.candidate.explicit_requested
    if explicit and (now - request.original_due).total_seconds() > 43200:
        return _result(request, scope, now, base, "app_inbox", "reminder_older_than_twelve_hours")
    if now < request.original_due:
        return _result(request, scope, now, base, "not_due", "not_due", request.original_due)
    if request.not_before is not None and now < request.not_before:
        return _result(request, scope, now, base, "deferred", "retry_not_due", request.not_before)
    if base.allowed:
        return _result(request, scope, now, base, "push", "ready")
    if request.candidate.kind == "brief" and request.brief_subscribed and base.reason == "quiet_hours":
        return _result(request, scope, now, base, "push", "subscribed_brief_quiet_exemption")
    disposition = "deferred" if base.next_due is not None else "blocked"
    return _result(request, scope, now, base, disposition, base.reason, base.next_due)


def recheck_delivery(
    plan: DeliveryPlan,
    request: DeliveryRequest,
    settings: FollowupSettings,
    state: ReceptivityState,
    *,
    scope: FollowupScope,
    clock: Clock,
    sent_today: int = 0,
) -> DeliveryPlan:
    if not isinstance(plan, DeliveryPlan) or not isinstance(request, DeliveryRequest):
        raise ValueError("delivery_plan_and_request_required")
    identity = (request.occurrence_id, request.candidate.id, request.candidate.kind, request.original_due)
    expected = (plan.occurrence_id, plan.candidate_id, plan.kind, plan.original_due)
    if plan.scope != scope or identity != expected or plan.request_key != request_key(request, scope):
        raise ValueError("delivery_occurrence_payload_changed")
    return plan_delivery(request, settings, state, scope=scope, clock=clock, sent_today=sent_today)

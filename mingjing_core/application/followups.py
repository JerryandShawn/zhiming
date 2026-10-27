"""Offline preparation plans. No scheduler, model, persistence, or outbound transport."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from mingjing_core.timekit.clock import Clock

from .followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
    aware,
)
from .followups_rules import decide_delivery


@dataclass(frozen=True)
class FollowupPlan:
    scope: FollowupScope
    entity_id: str
    due_at: datetime
    operation_id: str
    kind: str = "followup"
    lane: str = "background"


@dataclass(frozen=True)
class GeneratedFollowup:
    status: Literal["ready", "skipped"]
    text: str = field(repr=False)


def plan_followups(
    candidates: Sequence[FollowupCandidate],
    settings: FollowupSettings,
    state: ReceptivityState,
    *,
    scope: FollowupScope,
    clock: Clock,
) -> tuple[FollowupPlan, ...]:
    """Prepare active rows due within fifteen minutes; durable idempotency belongs to caller."""
    now = aware(clock.now())
    scope.require(state.owner_id, state.subject_id)
    seen, result = {}, []
    for candidate in candidates:
        scope.require(candidate.owner_id, candidate.subject_id)
        if candidate.id in seen:
            if seen[candidate.id] != candidate:
                raise ValueError("conflicting followup snapshot identity")
            continue
        seen[candidate.id] = candidate
        if candidate.kind == "brief" or candidate.due_at > now + timedelta(minutes=15):
            continue
        decision = decide_delivery(candidate, settings, state, scope=scope, clock=clock)
        # Quiet hours/cap must be evaluated at actual claim, not when preparing early.
        if decision.reason not in {"not_due", "ready", "quiet_hours", "daily_cap"}:
            continue
        operation = f"followup:{candidate.id}:{candidate.due_at.isoformat()}"
        result.append(FollowupPlan(scope, candidate.id, candidate.due_at, operation))
    return tuple(sorted(result, key=lambda plan: (plan.due_at, plan.entity_id)))


def classify_generated_followup(
    text: str, *, result_already_known: bool = False
) -> GeneratedFollowup:
    """No implicit side effects; SKIP and already-discussed outcomes never enter delivery."""
    if not isinstance(text, str) or type(result_already_known) is not bool:
        raise ValueError("invalid generated followup contract")
    if result_already_known or text.strip() == "SKIP":
        return GeneratedFollowup("skipped", "")
    if not text.strip() or len(text) > 3000:
        raise ValueError("empty or excessive generated followup")
    return GeneratedFollowup("ready", text.strip())

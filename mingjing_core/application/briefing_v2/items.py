"""Brief content does not execute notices; K2/inbox/quiet/cap limits remain visible selection gates."""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from mingjing_core.application.followups_contracts import FollowupScope, FollowupSettings, ReceptivityState
from mingjing_core.organize.spaces import DEFAULT_SPACES
from mingjing_core.scheduling.delivery_rules import plan_delivery
from mingjing_core.timekit.clock import FrozenClock

from .authorization import state_reason
from .contracts import BriefingError, BriefItem, BriefLine, BriefOmission, BriefSection

SPACES = {space.id: space.name for space in DEFAULT_SPACES}


def item_sections(
    items: Sequence[BriefItem],
    *,
    scope: FollowupScope,
    day: date,
    now: datetime,
    settings: FollowupSettings,
    receptivity: ReceptivityState,
    sent_today: int,
) -> tuple[tuple[BriefSection, ...], tuple[BriefOmission, ...]]:
    if not isinstance(items, (tuple, list)) or any(not isinstance(item, BriefItem) for item in items):
        raise BriefingError("brief_items_required")
    by_occurrence, groups, omissions = {}, {}, []
    used_followups = sent_today
    for item in sorted(items, key=lambda value: (value.request.original_due, value.request.occurrence_id)):
        occurrence = item.request.occurrence_id
        if occurrence in by_occurrence:
            if by_occurrence[occurrence] != item:
                raise BriefingError("brief_occurrence_payload_changed")
            continue
        by_occurrence[occurrence] = item
        line, reason, consumes = _item(item, scope, day, now, settings, receptivity, used_followups)
        if line is None:
            omissions.append(BriefOmission(item.request.candidate.id, reason))
            continue
        groups.setdefault(item.area_id, []).append(line)
        used_followups += consumes
    sections = tuple(
        BriefSection("area_" + (area or "unorganized"), SPACES.get(area, "待整理"), tuple(groups[area]))
        for area in (*SPACES, None)
        if area in groups
    )
    return sections, tuple(omissions)


def _item(
    item: BriefItem,
    scope: FollowupScope,
    day: date,
    now: datetime,
    settings: FollowupSettings,
    receptivity: ReceptivityState,
    sent_today: int,
) -> tuple[BriefLine | None, str | None, int]:
    candidate = item.request.candidate
    if (candidate.owner_id, candidate.subject_id) != (scope.owner_id, scope.subject_id):
        raise BriefingError("brief_candidate_scope_mismatch")
    if candidate.kind not in {"followup", "reminder"}:
        return None, "unsupported_brief_item_kind", 0
    reason = state_reason(item.basis, item.source_states, scope)
    if reason is not None:
        return None, reason, 0
    plan = plan_delivery(
        item.request, settings, receptivity, scope=scope, clock=FrozenClock(now), sent_today=sent_today
    )
    if plan.disposition not in {"push", "not_due"}:
        return None, plan.reason, 0
    due = item.request.original_due.astimezone(ZoneInfo(settings.timezone))
    if plan.disposition == "not_due" and due.date() >= day + timedelta(days=7 - day.weekday()):
        return None, "outside_current_week", 0
    if not candidate.text.strip():
        return None, "empty_brief_item", 0
    label = "明确提醒" if candidate.kind == "reminder" else "待跟进"
    when = due.strftime("%m-%d %H:%M")
    late = "；" + plan.late_note if plan.late_note else ""
    return (
        BriefLine(f"{when} {label}：{candidate.text[:1500]}{late}", item.basis),
        None,
        int(candidate.kind == "followup" and plan.allowed),
    )

"""Compose a subscribed brief using pure projections. A push plan is never a sending permission."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
    aware,
)
from mingjing_core.scheduling.brief_schedule import BriefSubscription, next_brief
from mingjing_core.scheduling.delivery_contracts import DeliveryPlan, DeliveryRequest
from mingjing_core.scheduling.delivery_rules import plan_delivery
from mingjing_core.timekit.clock import Clock, FrozenClock

from .authorization import state_reason, subscription_basis, transit_state_reason
from .calendar import calendar_section
from .contracts import (
    BasisRef,
    BriefEffects,
    BriefingError,
    BriefingResult,
    BriefItem,
    BriefLine,
    BriefSection,
    BriefSourceState,
    CalendarSnapshot,
)
from .current_manifest import validate_current_batch
from .items import item_sections
from .transit import transit_section

CLOSING = "今天先照顾好眼前的一件事，留一点余地给自己。"


def compose_briefing(
    *,
    scope: FollowupScope,
    subscription: BriefSubscription,
    settings: FollowupSettings,
    receptivity: ReceptivityState,
    calendar: CalendarSnapshot,
    clock: Clock,
    transit: Mapping[str, Any] | None = None,
    profile_revision: int | None = None,
    items: Sequence[BriefItem] = (),
    sent_today: int = 0,
    subscription_state: BriefSourceState | None = None,
    transit_state: BriefSourceState | None = None,
) -> BriefingResult:
    now = aware(clock.now())
    _inputs(scope, subscription, settings, receptivity, calendar, now)
    day = calendar.day
    key = "brief:" + fingerprint(
        [scope.owner_id, scope.subject_id, day.isoformat(), subscription.time_zone, subscription.revision]
    )
    basis = subscription_basis(subscription)
    reason = state_reason((basis,), (subscription_state,) if subscription_state is not None else (), scope)
    delivery, warnings = _delivery(scope, subscription, settings, receptivity, now, day, key, reason, sent_today)
    if delivery is None or delivery.disposition == "blocked":
        return BriefingResult(scope, day, calendar.timezone, now, (), (), delivery, (), warnings, key, "明镜的晨报到了")
    validate_current_batch(
        items,
        scope=scope,
        day=day,
        subscription_state=subscription_state,
        transit=transit,
        transit_state=transit_state,
        profile_revision=profile_revision,
    )
    sections = [calendar_section(calendar)]
    areas, omissions = item_sections(
        items, scope=scope, day=day, now=now, settings=settings, receptivity=receptivity, sent_today=sent_today
    )
    sections.extend(areas)
    transit_lines, transit_warnings = _transit(transit, transit_state, scope, day, profile_revision)
    if transit_lines is not None:
        sections.append(transit_lines)
    policy = BasisRef("p1", "briefing-v2-template", 1, scope.owner_id, scope.subject_id, fingerprint(CLOSING))
    sections.append(BriefSection("closing", "给今天的一句话", (BriefLine(CLOSING, (policy,)),)))
    all_basis = _basis((basis, *(ref for section in sections for line in section.lines for ref in line.basis)))
    return BriefingResult(
        scope,
        day,
        calendar.timezone,
        now,
        tuple(sections),
        all_basis,
        delivery,
        omissions,
        tuple(dict.fromkeys((*warnings, *transit_warnings))),
        key,
        "明镜的晨报到了",
        BriefEffects(),
    )


def _inputs(
    scope: FollowupScope,
    subscription: BriefSubscription,
    settings: FollowupSettings,
    receptivity: ReceptivityState,
    calendar: CalendarSnapshot,
    now: datetime,
) -> None:
    if (
        not isinstance(scope, FollowupScope)
        or not isinstance(subscription, BriefSubscription)
        or not isinstance(calendar, CalendarSnapshot)
    ):
        raise BriefingError("scoped_brief_inputs_required")
    if not isinstance(settings, FollowupSettings) or not isinstance(receptivity, ReceptivityState):
        raise BriefingError("current_brief_settings_required")
    if scope != subscription.scope or scope != calendar.scope:
        raise BriefingError("brief_scope_mismatch")
    scope.require(receptivity.owner_id, receptivity.subject_id)
    if subscription.time_zone != calendar.timezone or subscription.time_zone != settings.timezone:
        raise BriefingError("brief_timezone_mismatch")
    if now.astimezone(ZoneInfo(calendar.timezone)).date() != calendar.day:
        raise BriefingError("brief_calendar_day_mismatch")
    if not timedelta() <= now - calendar.observed_at <= timedelta(minutes=15):
        raise BriefingError("brief_calendar_snapshot_not_fresh")


def _delivery(
    scope: FollowupScope,
    subscription: BriefSubscription,
    settings: FollowupSettings,
    receptivity: ReceptivityState,
    now: datetime,
    day: date,
    key: str,
    source_reason: str | None,
    sent_today: int,
) -> tuple[DeliveryPlan | None, tuple[str, ...]]:
    anchor = datetime.combine(day, time(), ZoneInfo(subscription.time_zone)).astimezone(now.tzinfo)
    occurrence = next_brief(subscription, anchor - timedelta(microseconds=1), inclusive=True)
    if occurrence.at is None:
        return None, (occurrence.reason or "brief_time_needs_clarification",)
    if occurrence.at.astimezone(ZoneInfo(subscription.time_zone)).date() != day:
        return None, ("brief_occurrence_day_mismatch",)
    candidate = FollowupCandidate(
        key,
        scope.owner_id,
        scope.subject_id,
        "brief",
        occurrence.at,
        category="brief",
        active=subscription.enabled,
        source_active=source_reason is None,
        text="明镜的晨报到了",
    )
    request = DeliveryRequest(
        key, candidate, occurrence.at, brief_subscribed=subscription.enabled and source_reason is None
    )
    result = plan_delivery(request, settings, receptivity, scope=scope, clock=FrozenClock(now), sent_today=sent_today)
    return result, (source_reason,) if source_reason else ()


def _transit(
    payload: Mapping[str, Any] | None,
    state: BriefSourceState | None,
    scope: FollowupScope,
    day: date,
    revision: int | None,
) -> tuple[BriefSection | None, tuple[str, ...]]:
    if payload is None:
        return None, ("transit_unavailable",)
    reason = transit_state_reason(payload, state, scope, revision)
    if reason:
        return None, (reason,)
    try:
        section, warnings = transit_section(payload, scope=scope, day=day, profile_revision=revision)
        return section, (*warnings, "transit_aliases_local_registration_required")
    except (ValueError, TypeError, KeyError):
        return None, ("transit_invalid_or_unavailable",)


def _basis(refs: Sequence[BasisRef]) -> tuple[BasisRef, ...]:
    by_alias = {}
    for ref in refs:
        if ref.alias in by_alias and by_alias[ref.alias] != ref:
            raise BriefingError("brief_alias_collision")
        by_alias[ref.alias] = ref
    return tuple(by_alias.values())

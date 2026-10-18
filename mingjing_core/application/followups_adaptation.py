"""Deterministic response projections; short acknowledgements never increase contact frequency."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from mingjing_core.timekit.clock import Clock

from .followups_contracts import (
    FollowupScope,
    ProactiveNotice,
    ReceptivityState,
    ResponseObservation,
    ResponseStatus,
    UserActivity,
    aware,
)

BRIEF_PROMPT_OPTIONS = ("保持", "换个时间", "先停一周")
RESPONSE_WINDOW = timedelta(hours=24)
ADAPTATION_PAUSE = timedelta(days=7)
BRIEF_PROMPT_COOLDOWN = timedelta(days=30)


def classify_response(
    notice: ProactiveNotice,
    activities: Sequence[UserActivity],
    *,
    scope: FollowupScope,
    clock: Clock,
    muted_at: datetime | None = None,
) -> ResponseStatus:
    scope.require(notice.owner_id, notice.subject_id)
    now = aware(clock.now())
    if notice.sent_at > now:
        raise ValueError("不能为尚未发送的消息判定接收度")
    for event in activities:
        scope.require(event.owner_id, event.subject_id)
    if muted_at is not None:
        instant = aware(muted_at)
        if not notice.sent_at < instant <= now:
            raise ValueError("静音必须有发送后的有效用户操作时间")
        return "muted"
    deadline = notice.sent_at + RESPONSE_WINDOW
    if any(notice.sent_at < event.at <= min(deadline, now) for event in activities):
        return "replied"
    return "ignored" if now >= deadline else "pending"


def _observations(
    state: ReceptivityState, notice: ProactiveNotice, status: ResponseStatus, now: datetime
) -> tuple[ResponseObservation, ...]:
    existing = next((item for item in state.observations if item.notice.id == notice.id), None)
    if existing and existing.notice != notice:
        raise ValueError("同一主动消息标识不能更换元数据")
    if existing and (existing.status == status or status == "pending"):
        return state.observations
    # Reconciled historical responses can refine a previous projection; a pause already started remains in force.
    update = ResponseObservation(notice, status, now)
    return tuple(item for item in state.observations if item.notice.id != notice.id) + (update,)


def _ignored_streak(
    state: ReceptivityState, records: tuple[ResponseObservation, ...], now: datetime
) -> tuple[int, bool]:
    expired = state.pause_until is not None and now >= state.pause_until
    streak = state.ignored_streak if not state.observations and not expired else 0
    reached_two = False
    for item in sorted(records, key=lambda item: (item.notice.sent_at, item.notice.id)):
        if item.notice.kind == "reminder" or (expired and item.observed_at < state.pause_until):
            continue
        streak = min(2, streak + 1) if item.status == "ignored" else 0
        reached_two = reached_two or streak >= 2
    return streak, reached_two


def _brief_days(records: tuple[ResponseObservation, ...], timezone: str) -> tuple[date, ...]:
    zone = ZoneInfo(timezone)
    days: tuple[date, ...] = ()
    for item in sorted(records, key=lambda item: (item.notice.sent_at, item.notice.id)):
        if item.notice.kind != "brief" or item.status == "pending":
            continue
        day = item.notice.sent_at.astimezone(zone).date()
        if item.status != "ignored":
            days = ()
        elif not days or day > days[-1] + timedelta(days=1):
            days = (day,)
        elif day != days[-1]:
            days += (day,)
    return days


def apply_response(
    state: ReceptivityState,
    notice: ProactiveNotice,
    status: ResponseStatus,
    *,
    scope: FollowupScope,
    clock: Clock,
    timezone: str = "Asia/Shanghai",
) -> ReceptivityState:
    scope.require(state.owner_id, state.subject_id)
    scope.require(notice.owner_id, notice.subject_id)
    now = aware(clock.now())
    if notice.sent_at > now or status not in {"pending", "replied", "ignored", "muted"}:
        raise ValueError("主动消息响应状态无效")
    if status == "ignored" and now < notice.sent_at + RESPONSE_WINDOW:
        raise ValueError("未满24小时不能认定主动消息被忽略")
    for item in state.observations:
        scope.require(item.notice.owner_id, item.notice.subject_id)
    records = _observations(state, notice, status, now)
    if records is state.observations:
        return state
    streak, reached_two = _ignored_streak(state, records, now)
    until = state.pause_until
    if reached_two and (until is None or now >= until):
        until = now + ADAPTATION_PAUSE
    days = _brief_days(records, timezone)
    pending = state.brief_prompt_pending or (notice.kind == "brief" and status == "ignored" and len(days) >= 5)
    muted = state.muted_categories
    if status == "muted" and notice.category:
        muted = muted | {notice.category}
        if notice.kind == "brief":
            pending = False
    return replace(
        state,
        ignored_streak=streak,
        pause_until=until,
        brief_ignore_days=days,
        brief_prompt_pending=pending,
        muted_categories=frozenset(muted),
        observations=records,
    )


def brief_prompt_due(state: ReceptivityState, *, scope: FollowupScope, clock: Clock) -> bool:
    scope.require(state.owner_id, state.subject_id)
    now = aware(clock.now())
    return state.brief_prompt_pending and (
        state.brief_prompted_at is None or now >= state.brief_prompted_at + BRIEF_PROMPT_COOLDOWN
    )


def mark_brief_prompted(state: ReceptivityState, *, scope: FollowupScope, clock: Clock) -> ReceptivityState:
    if not brief_prompt_due(state, scope=scope, clock=clock):
        raise ValueError("晨报偏好提问尚未触发或仍在冷却")
    return replace(state, brief_prompt_pending=False, brief_prompted_at=aware(clock.now()))

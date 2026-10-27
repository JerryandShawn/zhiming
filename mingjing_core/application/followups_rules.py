"""Pure claim-time decisions; mainline must atomically claim counts and recheck source scope."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from mingjing_core.timekit.clock import Clock

from .followups_contracts import (
    DeliveryDecision,
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ProactiveNotice,
    ReceptivityState,
    aware,
)

SENSITIVE_PREVIEW = "明镜想问问你"
SENSITIVE_CATEGORIES = frozenset(
    {"health", "wellbeing", "medical", "money", "finance", "financial", "健康", "身心", "金钱", "财务"}
)


def count_followups_today(
    notices: Sequence[ProactiveNotice], *, scope: FollowupScope, clock: Clock, timezone: str = "Asia/Shanghai"
) -> int:
    now = aware(clock.now())
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()
    unique: dict[str, ProactiveNotice] = {}
    for notice in notices:
        scope.require(notice.owner_id, notice.subject_id)
        if notice.id in unique and unique[notice.id] != notice:
            raise ValueError("同一已发消息标识不能更换元数据")
        unique[notice.id] = notice
    return sum(
        notice.kind == "followup" and notice.sent_at <= now and notice.sent_at.astimezone(zone).date() == today
        for notice in unique.values()
    )


def safe_preview(text: str, category: str = "", *, proactive: bool = True, sensitive: bool = False) -> str:
    if not isinstance(text, str) or not isinstance(category, str):
        raise ValueError("预览与类别必须是文本")
    if type(proactive) is not bool or type(sensitive) is not bool:
        raise ValueError("预览开关无效")
    return (
        SENSITIVE_PREVIEW if proactive and (sensitive or category.strip().casefold() in SENSITIVE_CATEGORIES) else text
    )


def effective_daily_cap(settings: FollowupSettings, state: ReceptivityState, *, clock: Clock) -> int:
    return _cap_at(settings, state, aware(clock.now()))


def _cap_at(settings: FollowupSettings, state: ReceptivityState, now: datetime) -> int:
    return (
        min(settings.daily_cap, 1) if state.pause_until is not None and now < state.pause_until else settings.daily_cap
    )


def in_quiet_hours(local_time: time, settings: FollowupSettings) -> bool:
    stamp = local_time.replace(tzinfo=None)
    start, end = settings.quiet_start, settings.quiet_end
    return start <= stamp < end if start < end else stamp >= start or stamp < end


def _wall(day: date, at: time, zone: ZoneInfo) -> datetime:
    intended = datetime.combine(day, at, zone)
    # UTC round-tripping also handles locally nonexistent wall times and skipped civil dates.
    return intended.astimezone(UTC).astimezone(zone)


def _resume(at: datetime, settings: FollowupSettings, *, next_day: bool = False) -> datetime:
    zone = ZoneInfo(settings.timezone)
    local = at.astimezone(zone)
    day = local.date() + timedelta(days=int(next_day))
    if not next_day and settings.quiet_start > settings.quiet_end and local.time() >= settings.quiet_start:
        day += timedelta(days=1)
    candidate = _wall(day, settings.resume_at, zone)
    for _ in range(4):
        if candidate > at and not in_quiet_hours(candidate.timetz(), settings):
            return candidate.astimezone(UTC)
        day += timedelta(days=1)
        candidate = _wall(day, settings.resume_at, zone)
    raise ValueError("无法找到免打扰之外的恢复时刻")


def _denial(candidate: FollowupCandidate, settings: FollowupSettings, state: ReceptivityState) -> str | None:
    if candidate.source_revoked:
        return "source_revoked"
    if not candidate.source_active:
        return "source_inactive"
    if not candidate.active:
        return "inactive"
    explicit = candidate.kind == "reminder" and candidate.explicit_requested
    if candidate.kind == "reminder" and not explicit:
        return "reminder_not_requested"
    muted = {category.strip().casefold() for category in settings.muted_categories | state.muted_categories}
    if candidate.category.strip().casefold() in muted:
        return "category_muted"
    if explicit:
        return None
    if not settings.proactive_enabled:
        return "proactive_disabled"
    if candidate.kind == "followup" and not settings.followups_enabled:
        return "followups_disabled"
    return None


def decide_delivery(
    candidate: FollowupCandidate,
    settings: FollowupSettings,
    state: ReceptivityState,
    *,
    scope: FollowupScope,
    clock: Clock,
    sent_today: int = 0,
) -> DeliveryDecision:
    scope.require(candidate.owner_id, candidate.subject_id)
    scope.require(state.owner_id, state.subject_id)
    if type(sent_today) is not int or sent_today < 0:
        raise ValueError("当地主动消息日计数无效")
    now = aware(clock.now())
    cap = _cap_at(settings, state, now)
    preview = safe_preview(candidate.text, candidate.category, sensitive=candidate.sensitive)

    def decision(allowed: bool, due: datetime | None, reason: str) -> DeliveryDecision:
        return DeliveryDecision(allowed, due, reason, cap, preview)

    denial = _denial(candidate, settings, state)
    if denial:
        return decision(False, None, denial)
    if candidate.kind == "followup" and not candidate.essential and state.pause_until and now < state.pause_until:
        end = state.pause_until
        due = (
            _resume(end, settings)
            if in_quiet_hours(end.astimezone(ZoneInfo(settings.timezone)).timetz(), settings)
            else end
        )
        return decision(False, due, "adaptation_pause")
    if now < candidate.due_at:
        return decision(False, candidate.due_at, "not_due")
    quiet = in_quiet_hours(now.astimezone(ZoneInfo(settings.timezone)).timetz(), settings)
    if quiet and not (candidate.kind == "reminder" and candidate.explicit_quiet_time):
        return decision(False, _resume(now, settings), "quiet_hours")
    if candidate.kind == "followup" and sent_today >= cap:
        return decision(False, _resume(now, settings, next_day=True) if cap else None, "daily_cap")
    return decision(True, None, "ready")

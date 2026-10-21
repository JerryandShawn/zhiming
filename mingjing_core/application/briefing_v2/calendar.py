"""P2 owns calendar facts. This adapter formats snapshots without copying arrangements."""

from dataclasses import asdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.streaming.json_values import thaw_json
from mingjing_core.timekit.almanac import Almanac, almanac
from mingjing_core.timekit.calendar_cn import DayStatus, day_status
from mingjing_core.timekit.clock import Clock
from mingjing_core.timeparse.calendar_port import CalendarPort

from .contracts import BasisRef, BriefingError, BriefLine, BriefSection, CalendarSnapshot

ALMANAC_KEYS = frozenset(Almanac.__dataclass_fields__)


def validate_calendar(snapshot: CalendarSnapshot) -> None:
    if not isinstance(snapshot.scope, FollowupScope) or type(snapshot.day) is not date:
        raise BriefingError("calendar_scope_day_required")
    zone = ZoneInfo(snapshot.timezone)
    if snapshot.observed_at.astimezone(zone).date() != snapshot.day:
        raise BriefingError("calendar_observed_day_mismatch")
    value, status = snapshot.almanac, snapshot.day_status
    if set(value) != ALMANAC_KEYS or value["solar"] != snapshot.day.isoformat():
        raise BriefingError("calendar_solar_day_mismatch")
    if value["weekday"] != "星期" + "一二三四五六日"[snapshot.day.weekday()]:
        raise BriefingError("calendar_weekday_mismatch")
    if not isinstance(status, DayStatus) or type(status.is_off) is not bool:
        raise BriefingError("calendar_status_required")
    if status.kind not in {"workday", "weekend", "holiday", "adjusted_workday"} or status.source not in {
        "builtin",
        "override",
        "unpublished",
    }:
        raise BriefingError("calendar_status_invalid")
    if status.is_off != (status.kind in {"weekend", "holiday"}):
        raise BriefingError("calendar_day_kind_inconsistent")
    for key in ("festivals", "yi", "ji"):
        if not isinstance(value[key], tuple) or any(type(item) is not str for item in value[key]):
            raise BriefingError("calendar_text_list_invalid")
    lunar = value["lunar"]
    if not hasattr(lunar, "keys") or set(lunar) != {"year", "zodiac", "month", "day", "is_leap"}:
        raise BriefingError("calendar_lunar_invalid")
    if type(lunar["is_leap"]) is not bool or any(
        type(lunar[key]) is not str for key in ("year", "zodiac", "month", "day")
    ):
        raise BriefingError("calendar_lunar_invalid")
    term = value["jieqi"]
    if not hasattr(term, "keys") or set(term) != {"current", "current_at", "next", "next_at", "days_to_next"}:
        raise BriefingError("calendar_term_invalid")
    stamps = []
    for key in ("current_at", "next_at"):
        stamp = datetime.fromisoformat(term[key])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise BriefingError("calendar_term_time_required")
        stamps.append(stamp)
    if not stamps[0] <= snapshot.observed_at <= stamps[1]:
        raise BriefingError("calendar_term_snapshot_mismatch")
    if any(type(term[key]) is not str or not term[key].strip() for key in ("current", "next")):
        raise BriefingError("calendar_term_label_required")
    if type(term["days_to_next"]) is not int or term["days_to_next"] < 0:
        raise BriefingError("calendar_term_days_invalid")
    if term["days_to_next"] != (stamps[1].astimezone(zone).date() - snapshot.day).days:
        raise BriefingError("calendar_term_day_difference_mismatch")


def calendar_snapshot(
    *, scope: FollowupScope, clock: Clock, timezone: str = "Asia/Shanghai", calendar: CalendarPort | None = None
) -> CalendarSnapshot:
    now = clock.now()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise BriefingError("calendar_aware_clock_required")
    try:
        zone = ZoneInfo(timezone)
    except (TypeError, ValueError, KeyError):
        raise BriefingError("calendar_timezone_invalid") from None
    local = now.astimezone(zone)
    value = almanac(now, zone)
    status = calendar.day_status(local.date()) if calendar is not None else day_status(local.date())
    return CalendarSnapshot(scope, local.date(), timezone, now, value.to_dict(), status)


def calendar_basis(snapshot: CalendarSnapshot) -> BasisRef:
    value = {
        "day": snapshot.day.isoformat(),
        "timezone": snapshot.timezone,
        "observed_at": snapshot.observed_at.isoformat(),
        "almanac": thaw_json(snapshot.almanac),
        "day_status": asdict(snapshot.day_status),
    }
    digest = fingerprint(value)
    return BasisRef(
        "t1",
        "p2-timekit:" + snapshot.day.isoformat(),
        snapshot.revision,
        snapshot.scope.owner_id,
        snapshot.scope.subject_id,
        digest,
        "brief-calendar:" + digest,
        "/",
    )


def calendar_section(snapshot: CalendarSnapshot) -> BriefSection:
    basis, value, status = (calendar_basis(snapshot),), snapshot.almanac, snapshot.day_status
    lunar = value["lunar"]
    leap = "闰" if lunar["is_leap"] else ""
    line = f"{snapshot.day.isoformat()} {value['weekday']}；农历{leap}{lunar['month']}月{lunar['day']}。"
    label = {
        "workday": "工作日",
        "weekend": "周末休息日",
        "holiday": f"{status.holiday_name or '法定假日'}放假日",
        "adjusted_workday": f"{status.holiday_name or '假期'}调休上班日",
    }[status.kind]
    if status.source == "unpublished":
        label += "；当年放假及调休安排尚未公布，当前只按普通星期判断"
    term = value["jieqi"]
    observed = snapshot.observed_at.astimezone(ZoneInfo(snapshot.timezone))
    term_line = (
        f"据{observed:%H:%M}历法快照，当前节气{term['current']}；下一个节气{term['next']}，交节时刻{term['next_at']}。"
    )
    tradition = "传统黄历供文化参考：宜" + "、".join(value["yi"][:2]) + "；忌" + "、".join(value["ji"][:2]) + "。"
    return BriefSection(
        "calendar", "今日历法", tuple(BriefLine(text, basis) for text in (line, label + "。", term_line, tradition))
    )

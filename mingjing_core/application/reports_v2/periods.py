"""Keep v3's current-period interpretation and explicit owner-local civil day boundaries."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from mingjing_core.domain.report_schedules import report_period, report_period_bounds

from .contracts import ReportError, ReportPeriod


def period_for(kind: str, day: date, timezone: str = "Asia/Shanghai") -> ReportPeriod:
    if type(kind) is not str or kind not in {"weekly", "monthly", "quarterly"} or type(day) is not date:
        raise ReportError("period_kind_or_day_invalid")
    try:
        zone = ZoneInfo(timezone)
        bounds = report_period_bounds(kind, day)
        first, last = date.fromisoformat(bounds["start"]), date.fromisoformat(bounds["end"])
        start = datetime.combine(first, time(), zone).astimezone(UTC)
        end = datetime.combine(last + timedelta(days=1), time(), zone).astimezone(UTC)
        return ReportPeriod(kind, report_period(kind, day), timezone, first, last, start, end)
    except (ValueError, TypeError, OverflowError, KeyError):
        raise ReportError("period_timezone_or_boundary_invalid") from None


def includes_instant(period: ReportPeriod, start: datetime, end: datetime | None = None) -> bool:
    if end is None:
        return period.start <= start < period.end
    return start < period.end and end > period.start

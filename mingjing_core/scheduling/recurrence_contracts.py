"""Immutable calendar recurrence rules; delivery eligibility is a separate policy."""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

RuleKind = Literal["daily", "weekly", "monthly", "yearly", "workday", "offday", "lunar_monthly", "lunar_yearly"]


class RecurrenceError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__("重复提醒的时间规则无效")


def aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RecurrenceError("aware_instant_required")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class RecurrenceRule:
    kind: RuleKind
    local_time: time | None = None
    time_zone: str = "Asia/Shanghai"
    weekday: int | None = None
    day: int | None = None
    month: int | None = None
    include_leap: bool = True
    leap: bool = False
    day_filter: Literal["all", "workday", "offday"] = "all"
    missing: Literal["skip"] = "skip"
    gap_policy: Literal["clarify", "skip"] = "clarify"
    fold_policy: Literal["clarify", "earliest", "latest"] = "clarify"

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in {
            "daily",
            "weekly",
            "monthly",
            "yearly",
            "workday",
            "offday",
            "lunar_monthly",
            "lunar_yearly",
        }:
            raise RecurrenceError("rule_kind_unknown")
        if self.local_time is not None and (
            not isinstance(self.local_time, time) or self.local_time.tzinfo is not None
        ):
            raise RecurrenceError("local_time_must_be_naive")
        try:
            ZoneInfo(self.time_zone)
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            raise RecurrenceError("time_zone_invalid") from None
        if type(self.include_leap) is not bool or type(self.leap) is not bool:
            raise RecurrenceError("leap_flag_invalid")
        for value, lower, upper in ((self.weekday, 0, 6), (self.day, 1, 31), (self.month, 1, 12)):
            if value is not None and (type(value) is not int or not lower <= value <= upper):
                raise RecurrenceError("rule_integer_invalid")
        if (
            type(self.day_filter) is not str
            or self.day_filter not in {"all", "workday", "offday"}
            or self.missing != "skip"
        ):
            raise RecurrenceError("rule_calendar_policy_invalid")
        _required_fields(self)
        if (
            type(self.gap_policy) is not str
            or type(self.fold_policy) is not str
            or self.gap_policy not in {"clarify", "skip"}
            or self.fold_policy not in {"clarify", "earliest", "latest"}
        ):
            raise RecurrenceError("rule_dst_policy_invalid")


def _required_fields(rule: RecurrenceRule) -> None:
    expected = {
        "weekly": {"weekday"},
        "monthly": {"day"},
        "yearly": {"month", "day"},
        "lunar_monthly": {"day"},
        "lunar_yearly": {"month", "day"},
    }.get(rule.kind, set())
    if any(getattr(rule, name) is not None and name not in expected for name in ("weekday", "day", "month")):
        raise RecurrenceError("rule_field_not_applicable")
    if rule.leap and rule.kind != "lunar_yearly":
        raise RecurrenceError("leap_only_for_annual_lunar_rule")
    if rule.kind in {"workday", "offday"} and rule.day_filter not in {"all", rule.kind}:
        raise RecurrenceError("conflicting_day_filter")
    if rule.kind == "weekly" and rule.weekday is None:
        raise RecurrenceError("weekday_required")
    if rule.kind in {"monthly", "yearly", "lunar_monthly", "lunar_yearly"} and rule.day is None:
        raise RecurrenceError("month_day_required")
    if rule.kind in {"yearly", "lunar_yearly"} and rule.month is None:
        raise RecurrenceError("year_month_required")
    if rule.kind.startswith("lunar_") and rule.day is not None and rule.day > 30:
        raise RecurrenceError("lunar_day_invalid")
    if rule.kind == "yearly":
        # Leap-year validation accepts Feb 29 but rejects impossible April 31.
        try:
            datetime(2000, rule.month, rule.day)
        except (ValueError, TypeError):
            raise RecurrenceError("yearly_date_invalid") from None


@dataclass(frozen=True)
class NextTriggerResult:
    at: datetime | None
    candidates: tuple[datetime, ...] = ()
    needs_clarification: bool = False
    reason: str = "ready"
    calendar_source: str | None = None

    def __post_init__(self) -> None:
        if self.at is not None:
            object.__setattr__(self, "at", aware(self.at))
        if type(self.needs_clarification) is not bool:
            raise RecurrenceError("clarification_flag_invalid")
        object.__setattr__(self, "candidates", tuple(aware(item) for item in self.candidates))

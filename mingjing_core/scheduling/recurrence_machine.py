"""Strict bridge for the existing U4 recurrence strings, not a second natural-language parser."""

from datetime import time

from .recurrence_contracts import RecurrenceError, RecurrenceRule

_ALLOWED = {
    "daily": set(),
    "workday": set(),
    "offday": set(),
    "weekly": {"weekday"},
    "monthly": {"day", "missing"},
    "yearly": {"month", "day", "missing"},
    "lunar_monthly": {"day", "include_leap"},
    "lunar_yearly": {"month", "day", "leap"},
}


def parse_recurrence(
    expression: str, *, local_time: time | None = None, time_zone: str = "Asia/Shanghai"
) -> RecurrenceRule:
    if type(expression) is not str:
        raise RecurrenceError("machine_rule_text_required")
    name, separator, suffix = expression.partition(":")
    if name not in _ALLOWED or (separator and not suffix):
        raise RecurrenceError("machine_rule_invalid")
    values = {}
    for piece in suffix.split(";") if suffix else ():
        key, equal, raw = piece.partition("=")
        if not equal or key not in _ALLOWED[name] or key in values:
            raise RecurrenceError("machine_rule_field_invalid")
        if key in {"day", "month", "weekday"}:
            if not raw.isascii() or not raw.isdecimal():
                raise RecurrenceError("machine_rule_integer_invalid")
            values[key] = int(raw)
        elif key in {"leap", "include_leap"}:
            if raw not in {"true", "false"}:
                raise RecurrenceError("machine_rule_boolean_invalid")
            values[key] = raw == "true"
        else:
            values[key] = raw
    return RecurrenceRule(name, local_time, time_zone, **values)

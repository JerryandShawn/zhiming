"""Wall-clock occurrences are round-tripped rather than silently shifted through DST."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from .recurrence_contracts import NextTriggerResult, RecurrenceRule


def wall_instants(day: date, rule: RecurrenceRule) -> tuple[datetime, ...]:
    if rule.local_time is None:
        return ()
    naive = datetime.combine(day, rule.local_time.replace(fold=0))
    zone = ZoneInfo(rule.time_zone)
    values = set()
    for fold in (0, 1):
        wall = naive.replace(tzinfo=zone, fold=fold)
        instant = wall.astimezone(UTC)
        back = instant.astimezone(zone).replace(tzinfo=None, fold=0)
        if back == naive:
            values.add(instant)
    return tuple(sorted(values))


def resolve_wall(day: date, rule: RecurrenceRule, after: datetime, inclusive: bool) -> NextTriggerResult | None:
    if rule.local_time is None:
        return NextTriggerResult(None, needs_clarification=True, reason="local_time_required")
    values = wall_instants(day, rule)
    if not values:
        intended = datetime.combine(day, rule.local_time.replace(fold=0))
        local_after = after.astimezone(ZoneInfo(rule.time_zone)).replace(tzinfo=None, fold=0)
        if intended < local_after or (intended == local_after and not inclusive):
            return None
        if rule.gap_policy == "skip":
            return None
        return NextTriggerResult(None, needs_clarification=True, reason="nonexistent_local_time")
    if len(values) > 1 and rule.fold_policy != "clarify":
        values = (values[0] if rule.fold_policy == "earliest" else values[-1],)
    future = tuple(value for value in values if value > after or (inclusive and value == after))
    if not future:
        return None
    if len(values) > 1:
        return NextTriggerResult(None, future, True, "ambiguous_local_time")
    return NextTriggerResult(future[0])

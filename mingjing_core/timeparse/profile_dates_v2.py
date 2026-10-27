"""Opt-in profile dates from explicit, authenticated, current source projections only."""

from dataclasses import replace
from datetime import datetime, timedelta

from .calendar_helpers import day_candidate
from .calendar_port import CalendarPort, P2CalendarPort
from .contracts import ParseContext, TimeCandidate, TimeRangeResult, make_result
from .profile_calendar_v2 import ProfileOccurrence, anniversary_occurrence, occurrence_in_year
from .profile_contracts_v2 import ProfileDatePort, ProfileDateRecord, ProfileScope
from .profile_patterns_v2 import ProfileExpression, profile_expressions


def _unclear(ctx: ParseContext, expression: ProfileExpression, reason: str) -> TimeRangeResult:
    result = make_result(
        ctx,
        start=None,
        end=None,
        matched_text=expression.matched,
        confidence=0.2,
        needs_clarification=True,
        normalized_text="资料日期待确认",
        reason=reason,
    )
    return replace(result, span=expression.span)


def _trusted(record: object, scope: ProfileScope, key: str) -> bool:
    return (
        isinstance(record, ProfileDateRecord)
        and record.scope == scope
        and record.key == key
        and record.active
        and record.current
        and record.confirmed
        and not record.revoked
        and not record.incognito
        and record.revision == record.current_revision
    )


def _records(port: ProfileDatePort, scope: ProfileScope, key: str) -> tuple[ProfileDateRecord, ...]:
    values = port.lookup(scope, key)
    if not isinstance(values, (tuple, list)) or len(values) > 100:
        raise ValueError("profile_projection_invalid")
    return tuple(item for item in values if _trusted(item, scope, key))


def _record_key(record: ProfileDateRecord) -> tuple:
    return record.month, record.day, record.year, record.calendar_kind, record.leap_month


def _choose_year(
    record: ProfileDateRecord,
    expression: ProfileExpression,
    ctx: ParseContext,
    calendar: CalendarPort,
) -> ProfileOccurrence:
    if expression.anniversary is not None:
        result = anniversary_occurrence(record, expression.anniversary, calendar)
        if expression.year is not None and result.nominal is not None and result.nominal.year != expression.year:
            return ProfileOccurrence(result.days, "conflicting_profile_years", result.nominal)
        return result
    if expression.year is not None:
        return occurrence_in_year(record, expression.year, calendar)
    result = occurrence_in_year(record, ctx.local_date.year, calendar)
    if result.nominal is None:
        return result
    passed = result.nominal < ctx.local_date or (expression.strict_next and result.nominal == ctx.local_date)
    return occurrence_in_year(record, ctx.local_date.year + 1, calendar) if passed else result


def _result(ctx: ParseContext, expression: ProfileExpression, value: ProfileOccurrence) -> TimeRangeResult:
    try:
        days = tuple(day + timedelta(days=expression.offset_days) for day in value.days)
    except OverflowError:
        return _unclear(ctx, expression, "profile_calendar_unavailable")
    if value.reason is not None or len(days) != 1:
        result = _unclear(ctx, expression, value.reason or "profile_calendar_ambiguous")
        candidates = tuple(day_candidate(day, ctx, "资料日期过法候选", 0.5) for day in days)
        return replace(result, candidates=candidates)
    day = days[0]
    result = make_result(
        ctx,
        start=day,
        end=day + timedelta(days=1),
        matched_text=expression.matched,
        confidence=0.95,
        reason="confirmed_profile_date",
    )
    return replace(result, span=expression.span)


def _resolve(
    expression: ProfileExpression,
    ctx: ParseContext,
    scope: ProfileScope,
    profiles: ProfileDatePort,
    calendar: CalendarPort,
) -> TimeRangeResult:
    if expression.subject_unclear or expression.key is None:
        return _unclear(ctx, expression, "profile_subject_or_key_unclear")
    try:
        records = _records(profiles, scope, expression.key)
    except Exception:
        return _unclear(ctx, expression, "profile_port_unavailable")
    if not records:
        return _unclear(ctx, expression, "missing_current_confirmed_profile")
    if len({_record_key(record) for record in records}) != 1:
        return _unclear(ctx, expression, "conflicting_profile_records")
    try:
        value = _choose_year(records[0], expression, ctx, calendar)
    except Exception:
        return _unclear(ctx, expression, "profile_calendar_unavailable")
    return _result(ctx, expression, value)


def _multiple(ctx: ParseContext, results: tuple[TimeRangeResult, ...]) -> TimeRangeResult:
    expression = ProfileExpression(None, ctx.text, (0, len(ctx.text)))
    candidates = tuple(
        candidate for result in results for candidate in (result.candidates or ((result,) if result.start else ()))
    )
    return replace(_unclear(ctx, expression, "multiple_profile_dates"), candidates=candidates[:16])


def _recurring(result: TimeRangeResult, expression: ProfileExpression) -> TimeRangeResult:
    if not expression.recurring:
        return result
    candidates = result.candidates
    if result.start is not None:
        candidates = (
            *candidates,
            TimeCandidate(
                result.start,
                result.end,
                result.granularity,
                "point",
                min(result.confidence, 0.5),
                result.normalized_text,
                "仅作资料日期参考，尚非循环调度规则",
            ),
        )
    return replace(
        result,
        start=None,
        end=None,
        kind="recurring",
        recurrence=None,
        candidates=candidates,
        needs_clarification=True,
        confidence=min(result.confidence, 0.4),
        normalized_text="资料周期需要独立确认调度规则",
        reason=result.reason if result.needs_clarification else "unsupported_profile_recurrence",
    )


def parse_profile_date(
    text: str,
    ref_time: datetime,
    tz: str = "Asia/Shanghai",
    *,
    scope: ProfileScope | None = None,
    profiles: ProfileDatePort | None = None,
    calendar: CalendarPort | None = None,
) -> TimeRangeResult | None:
    """Ordinary text returns None without lookup; missing/untrusted profile context asks without dates.

    Unqualified annual dates include today; 下个/next requires a later day. Offsets are applied to
    that selected anchor literally, and never silently move reminders into another year.
    """
    ctx = ParseContext(ref_time, tz, text)
    if len(text) > 100_000:
        return None
    try:
        expressions = profile_expressions(text, ctx)
    except (ValueError, KeyError, OverflowError):
        return _unclear(ctx, ProfileExpression(None, text, (0, len(text))), "profile_modifier_invalid")
    if not expressions:
        return None
    representative = next((item for item in expressions if item.recurring), expressions[0])
    if not isinstance(scope, ProfileScope) or profiles is None:
        return _recurring(_unclear(ctx, representative, "missing_profile_context"), representative)
    port = calendar if calendar is not None else P2CalendarPort()
    results = tuple(_recurring(_resolve(item, ctx, scope, profiles, port), item) for item in expressions)
    return results[0] if len(results) == 1 else _recurring(_multiple(ctx, results), representative)

"""Explicit zones and AM/PM clocks; DST is round-tripped, never silently normalized."""

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .contracts import ParseContext, TimeCandidate, TimeRangeResult, make_result
from .english_helpers_v2 import LEFT, RIGHT, alternatives, exact_span, invalid

ZONE = (
    r"(?:[A-Za-z_]+/[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)?|"
    r"(?:UTC|GMT)[+-]\d{1,2}(?::?\d{2})?|[+-]\d{2}:\d{2}|UTC|GMT|CST|EST|PST|IST|BST|Z)"
)
CLOCK = re.compile(
    rf"(?:{LEFT}|(?<=\dT))" + rf"(?:at\s+)?(?:\d{{1,2}}(?::\d{{1,3}}(?::\d{{1,3}})?)?\s*(?:a\.?m\.?|p\.?m\.?)|"
    rf"\d{{1,2}}:\d{{1,3}}(?::\d{{1,3}})?|noon|midnight)"
    rf"(?:\s*{ZONE})?" + RIGHT,
    re.I,
)
ABBREVIATIONS = {
    "CST": ("Asia/Shanghai", "America/Chicago"),
    "EST": ("America/New_York", "Australia/Brisbane"),
    "PST": ("America/Los_Angeles", "Asia/Manila"),
    "IST": ("Asia/Kolkata", "Europe/Dublin"),
    "BST": ("Europe/London", "Asia/Dhaka"),
}


@dataclass(frozen=True)
class EnglishClock:
    span: tuple[int, int]
    hour: int
    minute: int
    second: int
    zones: tuple
    zone_name: str | None = None
    invalid_reason: str | None = None


def clock_atoms(ctx: ParseContext) -> list[EnglishClock]:
    result = []
    for match in CLOCK.finditer(ctx.text):
        suffix = ctx.text[match.end() :]
        if re.match(r"[+:/-]\S", suffix):
            end = match.end() + len(re.match(r"\S+", suffix).group())
            result.append(EnglishClock((match.start(), end), 0, 0, 0, (), invalid_reason="invalid_clock_or_timezone"))
            continue
        try:
            result.append(_clock(match, ctx))
        except (ValueError, KeyError):
            result.append(EnglishClock(match.span(), 0, 0, 0, (), invalid_reason="invalid_clock_or_timezone"))
    return result


def _clock(match: re.Match, ctx: ParseContext) -> EnglishClock:
    raw = re.sub(r"^at\s+", "", match.group(), flags=re.I).strip()
    zone_match = re.search(rf"{ZONE}$", raw, re.I)
    zone_name = zone_match.group() if zone_match else None
    if zone_match:
        raw = raw[: zone_match.start()].strip()
    period = re.search(r"([ap])\.?m\.?$", raw, re.I)
    if raw.lower() in {"noon", "midnight"}:
        hour, minute, second = (12 if raw.lower() == "noon" else 0), 0, 0
    else:
        digits = re.findall(r"\d+", raw)
        if any(len(value) > 2 for value in digits):
            raise ValueError("invalid_clock_component_width")
        numbers = list(map(int, digits))
        hour, minute, second = (numbers + [0, 0])[:3]
        if period:
            if not 1 <= hour <= 12:
                raise ValueError("invalid_12_hour_clock")
            hour = hour % 12 + (12 if period.group(1).lower() == "p" else 0)
    time(hour, minute, second)
    zones = _zones(zone_name, ctx)
    return EnglishClock(match.span(), hour, minute, second, zones, zone_name)


def _zones(name: str | None, ctx: ParseContext) -> tuple:
    if name is None:
        return (ctx.zone,)
    upper = name.upper()
    if upper in ABBREVIATIONS:
        return tuple(ZoneInfo(value) for value in ABBREVIATIONS[upper])
    if upper in {"UTC", "GMT", "Z"}:
        return (UTC,)
    match = re.fullmatch(r"(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?", upper)
    if match:
        hour, minute = int(match.group(2)), int(match.group(3) or 0)
        if hour > 23 or minute > 59:
            raise ValueError("invalid_utc_offset")
        offset = timedelta(hours=hour, minutes=minute) * (1 if match.group(1) == "+" else -1)
        return (timezone(offset),)
    return (ZoneInfo(name),)


def apply_clock(clock: EnglishClock, ctx: ParseContext, base: TimeRangeResult | None) -> TimeRangeResult:
    span = (min(base.span[0], clock.span[0]), max(base.span[1], clock.span[1])) if base and base.span else clock.span
    matched = ctx.text[slice(*span)]
    if clock.invalid_reason:
        return exact_span(invalid(ctx, matched, clock.invalid_reason), span, ctx)
    if base and (base.kind != "point" or base.granularity != "day" or base.start is None and not base.candidates):
        return exact_span(
            replace(base, needs_clarification=True, confidence=0.3, reason="date_not_single_civil_day"), span, ctx
        )
    days = (
        [value.start.astimezone(ctx.zone).date() for value in base.candidates if value.start]
        if base and base.candidates
        else []
    )
    if not days:
        days = [base.start.astimezone(ctx.zone).date() if base and base.start else ctx.local_date]
    results = [_wall(day, clock, zone, ctx, matched) for day in dict.fromkeys(days) for zone in clock.zones]
    if any(item.reason == "nonexistent_wall_clock" for item in results):
        return exact_span(next(item for item in results if item.reason == "nonexistent_wall_clock"), span, ctx)
    reason = (
        "timezone_abbreviation_ambiguous"
        if len(clock.zones) > 1
        else base.reason
        if base and base.needs_clarification
        else None
    )
    if reason or len(results) > 1:
        return exact_span(alternatives(ctx, matched, results, reason or "multiple_clock_dates"), span, ctx)
    result = results[0]
    if base is None and result.start is not None and result.start < ctx.ref_time:
        following = _wall(days[0] + timedelta(days=1), clock, clock.zones[0], ctx, matched)
        result = alternatives(ctx, matched, (result, following), "clock_date_unspecified")
    return exact_span(result, span, ctx)


def _wall(day, clock: EnglishClock, zone, ctx: ParseContext, matched: str) -> TimeRangeResult:
    naive = datetime.combine(day, time(clock.hour, clock.minute, clock.second))
    stamps = [naive.replace(tzinfo=zone, fold=fold).astimezone(UTC) for fold in (0, 1)]
    valid = sorted({stamp for stamp in stamps if stamp.astimezone(zone).replace(tzinfo=None, fold=0) == naive})
    reason = "nonexistent_wall_clock" if not valid else "ambiguous_wall_clock" if len(valid) > 1 else None
    options = valid or sorted(set(stamps))

    def label(value):
        return value.astimezone(zone).isoformat()

    return make_result(
        ctx,
        start=None if reason else options[0],
        end=None if reason else options[0],
        matched_text=matched,
        granularity="second" if clock.second else "minute",
        confidence=0.3 if reason else 0.95,
        normalized_text=" / ".join(label(value) for value in options),
        needs_clarification=bool(reason),
        reason=reason,
        candidates=tuple(
            TimeCandidate(value, value, "minute", confidence=0.3, normalized_text=label(value)) for value in options
        )
        if reason
        else (),
    )

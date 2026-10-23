"""Civil month, quarter and provisional academic-term interpretations."""

import re
from datetime import date, timedelta

from .contracts import ParseContext, TimeCandidate, TimeRangeResult, make_result
from .numerals import NUMBER, parse_number
from .relative import shifted_month


def _year(raw: str | None, ctx: ParseContext) -> int:
    if raw in {"今年", None}:
        return ctx.local_date.year
    if raw in {"明年", "去年", "后年", "前年"}:
        return ctx.local_date.year + {"明年": 1, "去年": -1, "后年": 2, "前年": -2}[raw]
    return int(raw.rstrip("年"))


def parse_civil_date(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    yearless = False
    match = re.search(
        r"(?<!\d)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)(?:[（(](?:周|星期)[一二三四五六日天][）)])?", text
    )
    if match:
        values = tuple(map(int, match.groups()))
    else:
        match = re.search(rf"(今年|明年|去年|后年|前年|\d{{4}}年)?({NUMBER})月({NUMBER})[日号]?", text)
        if not match:
            return None
        yearless = match.group(1) is None
        values = _year(match.group(1), ctx), parse_number(match.group(2)), parse_number(match.group(3))
    try:
        day = date(*values)
    except ValueError:
        return make_result(
            ctx,
            start=None,
            end=None,
            matched_text=match.group(),
            confidence=0,
            needs_clarification=True,
            reason="invalid_civil_date",
        )
    if yearless and day < ctx.local_date:
        return _yearless(day, ctx, match.group())
    return make_result(ctx, start=day, end=day + timedelta(days=1), matched_text=match.group())


def _yearless(day: date, ctx: ParseContext, matched: str) -> TimeRangeResult:
    options = [day]
    for distance in range(1, 9):
        try:
            options.append(day.replace(year=day.year + distance))
            break
        except ValueError:
            continue
    results = tuple(
        make_result(ctx, start=value, end=value + timedelta(days=1), matched_text=matched) for value in options
    )
    candidates = tuple(TimeCandidate(item.start, item.end, normalized_text=item.normalized_text) for item in results)
    return make_result(
        ctx,
        start=results[0].start,
        end=results[0].end,
        matched_text=matched,
        confidence=0.45,
        needs_clarification=True,
        candidates=candidates,
        reason="year_not_specified",
        normalized_text=" / ".join(item.normalized_text for item in results),
    )


def parse_month(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    match = re.search(
        rf"(?:(今年|明年|去年|\d{{4}}年)?({NUMBER})月|(下下|下|本|这|上)(?:个)?月|月)(初|中|末|底|上旬|中旬|下旬)", text
    )
    if match:
        year, month, shift, part = match.groups()
        anchor = ctx.local_date.replace(day=1)
        if month:
            try:
                anchor = date(_year(year, ctx), parse_number(month), 1)
            except ValueError:
                return make_result(
                    ctx,
                    start=None,
                    end=None,
                    matched_text=match.group(),
                    confidence=0,
                    needs_clarification=True,
                    reason="invalid_month",
                )
        elif shift:
            anchor = shifted_month(anchor, {"下下": 2, "下": 1, "本": 0, "这": 0, "上": -1}[shift])
        return _month_window(anchor, part, match.group(), ctx)
    bare = re.search(r"上旬|中旬|下旬", text)
    if bare:
        return _month_window(ctx.local_date.replace(day=1), bare.group(), bare.group(), ctx)
    match = re.search(r"(下下|下|本|这|上)(?:个)?月(?![初中末底上旬下旬\d一二三四五六七八九十])", text)
    if not match:
        return None
    anchor = shifted_month(
        ctx.local_date.replace(day=1), {"下下": 2, "下": 1, "本": 0, "这": 0, "上": -1}[match.group(1)]
    )
    return make_result(
        ctx,
        start=anchor,
        end=shifted_month(anchor, 1),
        matched_text=match.group(),
        granularity="month",
        kind="range",
        normalized_text=f"{anchor.year}年{anchor.month}月",
    )


def _month_window(anchor: date, part: str, matched: str, ctx: ParseContext) -> TimeRangeResult:
    lower = 1 if part in {"初", "上旬"} else 11 if part in {"中", "中旬"} else 21
    start = anchor.replace(day=lower)
    end = anchor.replace(day=lower + 10) if lower < 21 else shifted_month(anchor, 1)
    return make_result(
        ctx,
        start=start,
        end=end,
        matched_text=matched,
        granularity="day",
        kind="range",
        confidence=0.8,
        normalized_text=f"{start.isoformat()}至{end.isoformat()}（不含结束）",
    )


def parse_quarter(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    match = re.search(r"(今年|明年|去年|\d{4}年)?第?([一二三四1-4])季度", text)
    if match:
        year, raw = match.groups()
        quarter = parse_number(raw)
        start = date(_year(year, ctx), (quarter - 1) * 3 + 1, 1)
    else:
        match = re.search(r"(下|上|本|这)(?:个)?季度", text)
        if not match:
            return None
        anchor = date(ctx.local_date.year, ((ctx.local_date.month - 1) // 3) * 3 + 1, 1)
        start = shifted_month(anchor, {"下": 3, "上": -3, "本": 0, "这": 0}[match.group(1)])
    end = shifted_month(start, 3)
    return make_result(
        ctx,
        start=start,
        end=end,
        matched_text=match.group(),
        granularity="quarter",
        kind="range",
        normalized_text=f"{start.year}年第{(start.month - 1) // 3 + 1}季度",
    )


def parse_term(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    match = re.search(r"(?:(今年|明年|去年|\d{4}年)?(春季|秋季)|下|上|本|这)(?:个)?学期", text)
    if not match:
        return None
    year, season = match.groups()
    anchor = ctx.local_date
    if season:
        start = date(_year(year, ctx), 2 if season == "春季" else 9, 1)
    else:
        start = date(
            anchor.year if anchor.month >= 2 else anchor.year - 1, 9 if anchor.month >= 9 or anchor.month < 2 else 2, 1
        )
        if match.group().startswith("下"):
            start = date(start.year + (start.month == 9), 2 if start.month == 9 else 9, 1)
        if match.group().startswith("上"):
            start = date(start.year - (start.month == 2), 9 if start.month == 2 else 2, 1)
    end = date(start.year + 1, 2, 1) if start.month == 9 else date(start.year, 7, 1)
    result = make_result(
        ctx,
        start=start,
        end=end,
        matched_text=match.group(),
        granularity="term",
        kind="range",
        confidence=0.45,
        needs_clarification=True,
        reason="academic_calendar_required",
        normalized_text=f"约{start.isoformat()}至{end.isoformat()}（需确认校历）",
    )
    candidate = TimeCandidate(result.start, result.end, "term", "range", 0.45, result.normalized_text, "常见校历估计")
    return make_result(
        ctx,
        start=start,
        end=end,
        matched_text=match.group(),
        granularity="term",
        kind="range",
        confidence=0.45,
        needs_clarification=True,
        candidates=(candidate,),
        reason="academic_calendar_required",
        normalized_text=result.normalized_text,
    )


def parse_year(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    match = re.search(r"今年|明年|去年|后年|前年|\d{4}年", text)
    if not match:
        return None
    season = re.match(r"(?:的)?[春夏秋冬](?:天|季)?", text[match.end() :])
    if season:
        return make_result(
            ctx,
            start=None,
            end=None,
            matched_text=match.group() + season.group(),
            confidence=0,
            needs_clarification=True,
            reason="season_boundary_unconfirmed",
        )
    year = _year(match.group(), ctx)
    return make_result(
        ctx,
        start=date(year, 1, 1),
        end=date(year + 1, 1, 1),
        matched_text=match.group(),
        granularity="year",
        kind="range",
        normalized_text=f"{year}年",
    )

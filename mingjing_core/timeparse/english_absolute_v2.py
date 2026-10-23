"""Civil English date expressions delegate date validity and yearless handling to U4."""

import re

from .contracts import ParseContext, TimeRangeResult
from .english_helpers_v2 import LEFT, RIGHT, alternatives, exact_span, invalid, translated

MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
MONTH_NAMES = {name: index + 1 for index, name in enumerate(MONTHS)}
MONTH_NAMES.update({name[:3]: index + 1 for index, name in enumerate(MONTHS)})
MONTH_NAMES["sept"] = 9
MONTH = "(?:" + "|".join(sorted(MONTH_NAMES, key=len, reverse=True)) + r")\.?"
ORDINAL = r"(?:st|nd|rd|th)?"
ABSOLUTE = re.compile(
    LEFT + rf"(?:\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}|"
    rf"{MONTH}\s+\d{{1,2}}{ORDINAL}(?:\s*,?\s*\d{{4}})?|"
    rf"\d{{1,2}}{ORDINAL}\s+{MONTH}(?:\s*,?\s*\d{{4}})?)" + rf"(?:{RIGHT}|(?=T\d))",
    re.I,
)


def absolute_atoms(ctx: ParseContext, calendar=None) -> list[TimeRangeResult]:
    results = []
    for match in ABSOLUTE.finditer(ctx.text):
        try:
            value = _absolute(match.group(), ctx, calendar)
        except (ValueError, OverflowError):
            value = invalid(ctx, match.group(), "invalid_english_date")
        results.append(exact_span(value, match.span(), ctx))
    return results


def _absolute(raw: str, ctx: ParseContext, calendar) -> TimeRangeResult:
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", raw):
        return translated(raw, raw, ctx, calendar)
    if "/" in raw:
        return _slash(raw, ctx, calendar)
    match = re.search(MONTH, raw, re.I)
    month = MONTH_NAMES[match.group().lower().rstrip(".")]
    values = [int(value) for value in re.findall(r"\d+", raw)]
    day, year = values[0], values[1] if len(values) == 2 else None
    expression = f"{year}年" if year is not None else ""
    return translated(f"{expression}{month}月{day}日", raw, ctx, calendar)


def _slash(raw: str, ctx: ParseContext, calendar) -> TimeRangeResult:
    first, second, year = map(int, raw.split("/"))
    results = []
    for month, day in ((first, second), (second, first)):
        result = translated(f"{year:04}-{month:02}-{day:02}", raw, ctx, calendar)
        if result.start is not None and not any(item.start == result.start for item in results):
            results.append(result)
    if len(results) == 1:
        return results[0]
    if not results:
        return invalid(ctx, raw, "invalid_english_date")
    return alternatives(ctx, raw, results, "numeric_date_order_unspecified")

"""English labels only: every holiday/lunar lookup remains in the injected P2 port."""

import re

from .contracts import ParseContext, TimeRangeResult
from .english_helpers_v2 import LEFT, RIGHT, exact_span, translated

LABELS = {
    "new year's day": "元旦",
    "chinese new year": "春节",
    "lunar new year": "春节",
    "spring festival": "春节",
    "qingming": "清明",
    "tomb sweeping day": "清明",
    "labour day": "五一",
    "labor day": "五一",
    "dragon boat festival": "端午",
    "mid-autumn festival": "中秋",
    "national day": "国庆",
}
NAME = "(?:" + "|".join(re.escape(name) for name in sorted(LABELS, key=len, reverse=True)) + ")"
HOLIDAY = re.compile(
    LEFT + rf"(?:(\d{{4}})\s+)?(?:(before|after|during)\s+)?({NAME})"
    rf"(?:\s+(\d{{4}}))?" + RIGHT,
    re.I,
)


def calendar_atoms(ctx: ParseContext, calendar=None) -> list[TimeRangeResult]:
    results = []
    for match in HOLIDAY.finditer(ctx.text):
        leading, relation, label, trailing = match.groups()
        year = leading or trailing
        expression = (f"{year}年" if year else "") + LABELS[label.lower()]
        expression += {None: "", "before": "前", "after": "后", "during": "期间"}[
            relation.lower() if relation else None
        ]
        result = translated(expression, match.group(), ctx, calendar)
        results.append(exact_span(result, match.span(), ctx))
    return results

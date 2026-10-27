"""Recognize profile-relative date spans without accessing injected profile records."""

import re
from dataclasses import dataclass

from .calendar_helpers import chinese_number, specified_year
from .contracts import ParseContext

NUMBER = r"[零〇一二三四五六七八九十百两\d]{1,4}"
ANCHORS = re.compile(
    rf"生日(?:那天|当天)?|(?:结婚|入职)(?:纪念日|{NUMBER}(?:周年|年后))"
    r"|birthday|wedding\s+anniversary|(?:employment|work)\s+anniversary",
    re.I,
)
CUSTOM = re.compile(r"(?:[“「][^”」\n]{1,24}[”」]|[\u4e00-\u9fff]{1,16})纪念日")
PREFIX = re.compile(
    rf"(?:(?:今年|明年|去年|后年|前年|[12]\d{{3}}年|{NUMBER}年后)(?:的)?|我的|我们的|本人的|"
    r"下一个|下个|下次|my\s+|our\s+|next\s+|this\s+year'?s?\s*|next\s+year'?s?\s*|last\s+year'?s?\s*|\s)*$",
    re.I,
)
SUFFIX = re.compile(rf"(?:那天|当天|的时候)?(?:的)?(?:(?:提前|前|之后|后)({NUMBER})天|({NUMBER})天(前|后))?")
OTHER_PERSON = re.compile(
    r"(?:朋友|妈妈|爸爸|父母|同事|室友|他|她|某人|孩子|妻子|丈夫)(?:的)?$|[\u4e00-\u9fff]+的$"
    r"|\b(?:his|her|their)\s*$|\b\w+['’]s\s*$",
    re.I,
)
_CYCLE = (
    r"(?:每(?:年|月|周|天|日|星期|个(?:月|周|星期))(?:的)?"
    r"|(?:every|each)\s+(?:(?:other|\d+)\s+)?(?:year|month|week|day)s?\b)"
)
CYCLE_HEAD = re.compile(_CYCLE + r"(?:\s+on)?\s*$", re.I)
CYCLE_TAIL = re.compile(r"^\s*" + _CYCLE, re.I)


@dataclass(frozen=True)
class ProfileExpression:
    key: str | None
    matched: str
    span: tuple[int, int]
    year: int | None = None
    strict_next: bool = False
    anniversary: int | None = None
    offset_days: int = 0
    subject_unclear: bool = False
    recurring: bool = False


def number(value: str) -> int:
    value = value.replace("两", "二")
    if "百" in value:
        hundreds, tail = value.split("百", maxsplit=1)
        return chinese_number(hundreds) * 100 + (chinese_number(tail.lstrip("零〇")) if tail.strip("零〇") else 0)
    return chinese_number(value)


def _modifiers(text: str, start: int, end: int, key: str | None, ctx: ParseContext) -> ProfileExpression:
    prefix = PREFIX.search(text[:start])
    lower = prefix.start() if prefix is not None else start
    suffix = SUFFIX.match(text[end:])
    upper = end + suffix.end() if suffix else end
    cycle_head, cycle_tail = CYCLE_HEAD.search(text[:lower]), CYCLE_TAIL.match(text[upper:])
    if cycle_head:
        lower = cycle_head.start()
    if cycle_tail:
        upper += cycle_tail.end()
    subject_unclear = bool(OTHER_PERSON.search(text[:lower]))
    matched = text[lower:upper]
    years = re.findall(r"前年|去年|今年|明年|后年|[12]\d{3}(?=年)", matched)
    year = specified_year(years[0], ctx) if len(years) == 1 else None
    relative = re.search(rf"({NUMBER})年后的?", text[lower:start])
    if relative is not None:
        year = ctx.local_date.year + number(relative[1])
    folded = matched.casefold()
    if "next year" in folded:
        year = ctx.local_date.year + 1
    elif "last year" in folded:
        year = ctx.local_date.year - 1
    elif "this year" in folded:
        year = ctx.local_date.year
    ordinal = re.search(rf"({NUMBER})(?:周年|年后)", text[start:end])
    anniversary = number(ordinal[1]) if ordinal else None
    offset = 0
    if suffix and (suffix[1] or suffix[2]):
        offset = number(suffix[1] or suffix[2])
        if "提前" in suffix.group() or "前" in suffix.group():
            offset = -offset
    strict = bool(re.search(r"下一个|下个|下次|\bnext\b", folded)) and "next year" not in folded
    return ProfileExpression(
        key,
        matched,
        (lower, upper),
        year,
        strict,
        anniversary,
        offset,
        subject_unclear,
        bool(cycle_head or cycle_tail),
    )


def _key(anchor: str) -> str:
    folded = anchor.casefold()
    if "生日" in anchor or "birthday" in folded:
        return "birthday"
    if "结婚" in anchor or "wedding" in folded:
        return "wedding_anniversary"
    return "employment_anniversary"


def _custom(
    text: str, match: re.Match, existing: list[ProfileExpression], ctx: ParseContext
) -> ProfileExpression | None:
    if any(item.span[1] == match.end() for item in existing):
        return None
    raw = match.group().removesuffix("纪念日")
    if raw.startswith(("“", "「")):
        name = raw[1:-1]
        lower = match.start()
    else:
        overlaps = [item.span[1] for item in existing if match.start() < item.span[1] < match.end()]
        raw = text[max(overlaps, default=match.start()) : match.end()].removesuffix("纪念日")
        name = re.split(
            r"我们的|我的|今年|明年|去年|下一个|下个|庆祝|记得|关于|聊聊|以及|还有|和|还是|或"
            r"|每(?:年|月|周|天|日|星期|个(?:月|周|星期))(?:的)?",
            raw,
        )[-1]
        lower = text.rfind(name, match.start(), match.end()) if name else match.start()
    key = "custom:" + name if name and name not in {"结婚", "入职", "一个", "那个", "周年"} else None
    return _modifiers(text, lower, match.end(), key, ctx)


def profile_expressions(text: str, ctx: ParseContext) -> tuple[ProfileExpression, ...]:
    result = [
        _modifiers(text, match.start(), match.end(), _key(match.group()), ctx) for match in ANCHORS.finditer(text)
    ]
    for match in CUSTOM.finditer(text):
        expression = _custom(text, match, result, ctx)
        if expression is not None:
            result.append(expression)
    if not result:
        match = re.search(r"纪念日|anniversary", text, re.I)
        if match:
            result.append(_modifiers(text, match.start(), match.end(), None, ctx))
    return tuple(sorted(result, key=lambda item: item.span))

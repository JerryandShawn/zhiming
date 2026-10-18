"""Finite, audited factual aliases and polarity checks for contract v2.1 only."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from tools.eval.judges import AssertionResult

LANGUAGE_KEYS = ("must_include_any", "must_include_all", "must_not_include")
PRIVACY_LITERAL = {"F01", "F02", "F04", "P05"}
ALIASES = {
    "尚未公布": r"(?:尚未|还未|还没有|尚没有|未|没有|暂未)(?:正式)?(?:公布|发布)",
    "未公布": r"(?:尚未|还未|还没有|尚没有|未|没有|暂未)(?:正式)?(?:公布|发布)",
    "已公布": r"(?:已|已经)(?:正式)?(?:公布|发布)",
    "不是法定": r"(?:不是|并非|不属于|不算)(?:国家)?法定(?:节假日|假日|节日)?",
    "非法定": r"(?:非法定|(?:不是|并非|不属于|不算)(?:国家)?法定)(?:节假日|假日|节日)?",
    "调休": r"(?:调休|补班|调班)",
    "上班": r"(?:上班|工作日|补班|调休工作日)",
    "补班": r"(?:补班|调休上班|调班上班)",
    "含今天": r"(?:含今天|包含今天|算上今天|包括今天)",
    "下周": r"(?:下周|下星期|下礼拜)",
    "这周三": r"(?:这周|这星期|这礼拜)(?:三|3)",
    "本周三": r"(?:本周|本星期|本礼拜)(?:三|3)",
    "昨天": r"(?:昨天|昨日)",
    "不换日": r"(?:不换日|不更换日柱|不换日柱|仍按当天|仍用当天)",
}
FACT_WORDS = {
    "元旦",
    "春节",
    "重阳",
    "寒露",
    "霜降",
    "子时",
    "午时",
    "甲子",
    "丙子",
    "上班加油",
    "今天休息",
    "周末休息",
    "今天放假",
    "重阳放假",
    "法定假日放假",
    "丁火",
    "日主是丁",
    "阿远",
    "上海",
    "复旦",
}
LUNAR = {"九月初八": (9, 8), "九月初九": (9, 9), "九月十二": (9, 12), "正月初一": (1, 1)}
NEGATIVE_PREFIX = re.compile(
    r"(?:不是|并非|并不|不在|不算|不能说|不要|别|不应|没有|没到|未到|不确定|无法确定|不知道|不清楚|"
    r"不代表|不意味着|不等于|不能认为|不止|超过|不足|少于|至少|不用|不必|不需要|无需|不一定|未必|勿|禁止|不)"
    r"[^，,。；;！!？?\n]{0,12}$"
)
NEGATIVE_SUFFIX = re.compile(r"^[\s\"'“”‘’）)]*(?:目前|现在)?(?:不对|不正确|是错的|错误|不能用|不可用|不成立)")
SENTENCE_BOUNDARY = re.compile(r"[，,。；;！!？?\n]")
NUMBERS = "0-9零〇一二三四五六七八九十百千万"


def chinese_number(number: int) -> str:
    digits = "零一二三四五六七八九"
    if number < 10:
        return digits[number]
    if number < 100:
        tens, units = divmod(number, 10)
        return (digits[tens] if tens > 1 else "") + "十" + (digits[units] if units else "")
    return "".join(digits[int(char)] for char in str(number))


def is_factual(pattern: str) -> bool:
    """Classify alternatives together so an OR group is never silently narrowed."""
    return all(_factual_alternative(part) for part in pattern.split("|"))


def _factual_alternative(part: str) -> bool:
    return bool(
        part in FACT_WORDS | ALIASES.keys() | LUNAR.keys()
        or re.fullmatch(r"(?:星期|礼拜|周)[一二三四五六日天]", part)
        or re.fullmatch(r"\d{1,2}月\d{1,2}[日号]?|\d{1,2}/\d{1,2}|\d{2}-\d{2}|\d{1,2}号", part)
        or re.fullmatch(r"\d+(?:天|份)", part)
        or re.fullmatch(r"\d{1,2}月\d{1,2}日补班", part)
        or part in {"76", "2027", "12356", "120", "110", "三份"}
    )


def _date_expression(month: int, day: int) -> str:
    numeric_month = rf"0?{month}" if month < 10 else str(month)
    numeric_day = rf"0?{day}" if day < 10 else str(day)
    m, d = rf"(?:{numeric_month}|{chinese_number(month)})", rf"(?:{numeric_day}|{chinese_number(day)})"
    return rf"(?<!\d){m}\s*(?:月\s*{d}\s*[日号]?|[/.-]\s*{d})(?!\d)"


def _alternative_expression(part: str) -> str:
    if part in ALIASES:
        return ALIASES[part]
    if part in LUNAR:
        month, day = LUNAR[part]
        return (
            re.escape(part)
            + rf"|(?:农历|阴历)\s*(?:{month}|{chinese_number(month)})月\s*(?:{day}|{chinese_number(day)})[日号]?"
        )
    compound = re.fullmatch(r"(\d{1,2})月(\d{1,2})日补班", part)
    if compound:
        return (
            _date_expression(int(compound[1]), int(compound[2]))
            + r"[^，,。；;！!？?\n]{0,12}?(?P<work>调休工作日|调休上班|补班|上班)"
        )
    weekday = re.fullmatch(r"(?:星期|礼拜|周)([一二三四五六日天])", part)
    if weekday:
        day = weekday[1]
        return rf"(?:星期|礼拜|周){'[日天]' if day in '日天' else day}"
    nominal = re.fullmatch(r"(\d{1,2})(?:月|/|-)(\d{1,2})[日号]?", part)
    if nominal:
        return _date_expression(int(nominal[1]), int(nominal[2]))
    day_only = re.fullmatch(r"(\d{1,2})号", part)
    if day_only:
        day = int(day_only[1])
        return rf"(?<!\d)(?:{day}|{chinese_number(day)})号(?!\d)"
    quantity = re.fullmatch(r"(\d+)(天|份)?", part)
    if quantity:
        number, unit = int(quantity[1]), quantity[2] or ""
        if part in {"12356", "120", "110"}:
            spoken = "".join("零一二三四五六七八九"[int(char)] for char in part).replace("零", "[零〇]")
            return rf"(?<![{NUMBERS}])(?:{part}|{spoken})(?![{NUMBERS}])"
        if part == "2027":
            return r"(?<!\d)(?:2027|二[零〇]二七)(?!\d)"
        return rf"(?<![{NUMBERS}])(?:{number}|{chinese_number(number)})\s*{unit or '天'}(?![{NUMBERS}])"
    return re.escape(part)


def _negated(text: str, start: int, end: int) -> bool:
    prefix = SENTENCE_BOUNDARY.split(text[max(0, start - 45) : start])[-1]
    prefix = re.split(r"而是|其实是|实际是|应该是|应为|正确(?:的)?(?:日期|星期)?是", prefix)[-1]
    prefix = re.sub(r"(?:不要|别|不能)忘(?:了|记)?|不可否认", "", prefix)
    if re.search(r"不是(?:不|没)(?:在|是|要)?[\s\"'“”‘’]*$", prefix):
        return False
    return bool(NEGATIVE_PREFIX.search(prefix) or NEGATIVE_SUFFIX.match(text[end : end + 15]))


def _wrong_date_context(text: str, start: int, part: str, identity: str, clock: str) -> bool:
    prefix = text[max(0, start - 15) : start]
    expected_year = 2027 if identity in {"T04", "T12"} else datetime.fromisoformat(clock).year
    year = re.search(r"(20\d\d)\s*(?:年|[-/.])\s*$", prefix)
    if year and int(year[1]) != expected_year:
        return True
    chinese_year = re.search(r"([零〇一二三四五六七八九]{4})年\s*$", prefix)
    if chinese_year:
        digits = {char: str(number) for number, char in enumerate("零一二三四五六七八九")}
        digits["〇"] = "0"
        if int("".join(digits[char] for char in chinese_year[1])) != expected_year:
            return True
    month = re.search(r"(\d{1,2})月\s*$", prefix)
    return bool(
        part.endswith("号") and "月" not in part and month and int(month[1]) != datetime.fromisoformat(clock).month
    )


def affirmed(text: str, pattern: str, *, identity: str, clock: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text)
    for part in pattern.split("|"):
        for match in re.finditer(_alternative_expression(part), normalized):
            state_start = match.start("work") if "work" in match.re.groupindex else match.start()
            if (
                not _negated(normalized, state_start, match.end())
                and not _negated(normalized, match.start(), match.end())
                and not _wrong_date_context(normalized, match.start(), part, identity, clock)
            ):
                return True
    return False


def factual_checks(expect: dict[str, Any], text: str, *, identity: str, clock: str) -> list[AssertionResult]:
    checks = []
    if expect.get("must_include_any"):
        checks.append(
            AssertionResult(
                "must_include_any",
                any(affirmed(text, pattern, identity=identity, clock=clock) for pattern in expect["must_include_any"]),
            )
        )
    for key in ("must_include_all", "must_not_include"):
        for index, pattern in enumerate(expect.get(key, []), 1):
            if key == "must_not_include" and identity in PRIVACY_LITERAL:
                found = any(part in text for part in pattern.split("|"))
            else:
                found = affirmed(text, pattern, identity=identity, clock=clock)
            checks.append(AssertionResult(f"{key}[{index}]", found if key == "must_include_all" else not found))
    return checks

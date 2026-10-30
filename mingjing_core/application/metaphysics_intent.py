"""Single P8 disclosure intent from unquoted user text, never consent."""

from __future__ import annotations

import re
from typing import Literal

from mingjing_core.memory.policy import mask_quoted

MetaphysicsIntent = Literal["none", "synastry", "window", "almanac", "daily"]
PURPOSES = r"签约|面试|搬家|出行|表白|开业"
# An explicit absolute date range, e.g. "2026-10-21到10-27" or "10月21日至10月27日".
DATE = r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日|\d{1,2}-\d{1,2})"
DATE_RANGE = DATE + r"\s*(?:到|至|~|—|-)\s*" + DATE
NEGATED = re.compile(r"不要|不用|不想|不需要|不许|禁止|别|无需")
PATTERNS = (
    ("synastry", re.compile(r"合盘|合不合|配不配|我和[他她].{0,12}(?:八字|星盘)")),
    (
        "window",
        re.compile(
            r"择日|挑(?:个)?日子|(?:哪天|哪几天|什么时候|何时).{0,12}(?:适合|宜).{0,8}(?:" + PURPOSES + r")"
            # A date range alone is not enough: it must also name a purpose or ask "which day".
            r"|" + DATE_RANGE + r".{0,12}(?:哪天|哪几天|" + PURPOSES + r")"
        ),
    ),
    ("almanac", re.compile(r"老?黄历|宜忌|冲煞")),
    (
        "daily",
        re.compile(r"(?:今天|明天).{0,12}(?:运势|流日|顺不顺)"),
    ),
)


def affirmative_clauses(text: str) -> list[str]:
    # Negation applies to its clause, so declining one capability cannot hide a
    # later explicit request for a different capability.
    unquoted = mask_quoted(re.sub(r"‘[^’\n]*’", lambda match: " " * len(match.group()), text))
    clauses = re.split(r"[，,。！？!?；;\n]|但是|不过|而是", unquoted)
    return [clause for clause in clauses if not NEGATED.search(clause)]


def daily_offsets(text: str) -> set[int]:
    if metaphysics_intent(text) != "daily":
        return set()
    return {
        int(word == "明天")
        for clause in affirmative_clauses(text)
        for match in PATTERNS[-1][1].finditer(clause)
        for word in re.findall(r"今天|明天", match[0])
    }


def metaphysics_intent(text: str, *, morning_report: bool = False) -> MetaphysicsIntent:
    """Higher priority affirmative clauses win; quoted/negated text opens nothing."""
    affirmative = affirmative_clauses(text)
    for intent, pattern in PATTERNS:
        if any(pattern.search(clause) for clause in affirmative):
            return intent
    # R36: scheduled reports need P7's trusted entry, not a boolean disclosure bypass.
    return "none"

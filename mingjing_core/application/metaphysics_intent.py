"""Single P8 disclosure intent from unquoted user text, never consent."""

from __future__ import annotations

import re
from typing import Literal

from mingjing_core.memory.policy import mask_quoted

MetaphysicsIntent = Literal["none", "synastry", "window", "almanac", "daily"]
PURPOSES = r"签约|面试|搬家|出行|表白|开业"
NEGATED = re.compile(r"不要|不用|不想|不需要|不许|禁止|别|无需")
PATTERNS = (
    ("synastry", re.compile(r"合盘|合不合|配不配|我和[他她].{0,12}(?:八字|星盘)")),
    (
        "window",
        re.compile(r"择日|挑(?:个)?日子|(?:哪天|哪几天|什么时候|何时).{0,12}(?:适合|宜).{0,8}(?:" + PURPOSES + r")"),
    ),
    ("almanac", re.compile(r"老?黄历|宜忌|冲煞")),
    (
        "daily",
        re.compile(r"(?:今天|明天|\d{4}-\d{2}-\d{2}|\d{1,2}月\d{1,2}[日号]).{0,12}(?:运势|流日|顺不顺)"),
    ),
)


def metaphysics_intent(text: str, *, morning_report: bool = False) -> MetaphysicsIntent:
    """Higher priority affirmative clauses win; quoted/negated text opens nothing."""
    # Negation applies to its clause, so declining one capability cannot hide a
    # later explicit request for a different capability.
    unquoted = mask_quoted(re.sub(r"‘[^’\n]*’", lambda match: " " * len(match.group()), text))
    clauses = re.split(r"[，,。！？!?；;\n]|但是|不过|而是", unquoted)
    affirmative = [clause for clause in clauses if not NEGATED.search(clause)]
    for intent, pattern in PATTERNS:
        if any(pattern.search(clause) for clause in affirmative):
            return intent
    return "daily" if morning_report else "none"

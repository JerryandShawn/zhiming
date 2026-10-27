"""Narrow lexical opposition candidates; never an embedding or truth verdict."""

from __future__ import annotations

import re
import unicodedata

_STANCE = re.compile(r"不再喜欢|不喜欢|不喜爱|不爱|讨厌|厌恶|喜欢|喜爱|热爱")
_NEGATIVE = frozenset({"不再喜欢", "不喜欢", "不喜爱", "不爱", "讨厌", "厌恶"})
_QUALIFIER = re.compile(r"但|不过|除了|除非|假如|假设|如果|比如|[?？]")
_TEMPORAL = re.compile(r"^(?:我(?:最近|现在|目前|如今)|(?:最近|现在|目前|如今)我)$")


def _signature(text: str) -> tuple[str, bool] | None:
    if not isinstance(text, str) or not 1 <= len(text) <= 3000 or _QUALIFIER.search(text):
        return None
    text = unicodedata.normalize("NFKC", text).casefold()
    matches = list(_STANCE.finditer(text))
    if len(matches) != 1:
        return None
    stance = matches[0]
    prefix = _TEMPORAL.sub("我", text[: stance.start()])
    topic = re.sub(r"\s+", " ", prefix + text[stance.end() :]).strip(" 。！!？?；;.")
    return (topic, stance[0] in _NEGATIVE) if len(topic) >= 3 else None


def opposing_preferences(previous: str, incoming: str) -> bool:
    """Only exact remaining topic text with opposite preference wording qualifies.

    Lack of a candidate does not establish consistency. Compound assertions,
    changing qualifiers, vague semantics and other kinds remain unclassified.
    """
    before, after = _signature(previous), _signature(incoming)
    return before is not None and after is not None and before[0] == after[0] and before[1] != after[1]

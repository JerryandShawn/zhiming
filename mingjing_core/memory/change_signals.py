"""R14: bounded self-reported changes for the two pending KU contracts."""

from __future__ import annotations

import re

from mingjing_core.memory.policy import has_optout, mask_quoted
from mingjing_core.memory.slots import compatible_statement

_UNSAFE = re.compile(r"如果|假如|假设|比如|也许|可能|不确定|听说|出差|旅游|临时|暂住|[?？，,；;\n]")
_CITY = re.compile(r"我(?:(?:现在|目前)?在(.{1,12}?)(?:工作|上班|居住|生活)|(?:现在)?住在(.{1,12}))")
_MOVE = re.compile(r"(?:我)?(?:最近|现在|已经)?搬到(.{1,12}?)了")
_SPICE_CHANGE = re.compile(
    r"(?:我)?(?:(?:最近)?开始(?:能|可以)吃(?:点|一点)?辣了|现在(?:不|能|可以)吃(?:点|一点)?辣了)"
)


def _assertion(text: str) -> str | None:
    if not isinstance(text, str) or not 1 <= len(text) <= 200:
        return None
    if _UNSAFE.search(text) or has_optout(text) or mask_quoted(text) != text:
        return None
    return text.strip().rstrip("。.!！")


def explicit_replacement_slot(previous: str, incoming: str) -> str | None:
    """No model hint, date invention or general semantic similarity is admitted.

    R14 explicitly authorizes a self-reported relocation to replace the unique
    previous city, including the old 'work in city' wording in KU01. Other
    ambiguities remain for the existing confirmation path.
    """
    before, after = _assertion(previous), _assertion(incoming)
    if before is None or after is None:
        return None
    city, moved = _CITY.fullmatch(before), _MOVE.fullmatch(after)
    if city and moved and moved[1] != (city[1] or city[2]):
        return "residence_city"
    if (
        _SPICE_CHANGE.fullmatch(after)
        and compatible_statement("spice_preference", before)
        and before.startswith("我")
        and before != after
    ):
        return "spice_preference"
    return None

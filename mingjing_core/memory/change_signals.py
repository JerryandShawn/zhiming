"""R14: bounded self-reported changes for the two pending KU contracts."""

from __future__ import annotations

import re

from mingjing_core.memory.policy import has_optout, mask_quoted
from mingjing_core.memory.slots import compatible_statement

_UNSAFE = re.compile(
    r"如果|假如|假设|比如|也许|可能|不确定|听说|出差|旅游|临时|暂住|试吃|代班|[?？]|"
    r"(?:朋友|同事|妈妈|爸爸|伴侣).*(?:说|表示)|据说|他说|她说"
)
_CITY = re.compile(r"我(?:(?:现在|目前)?在(.{1,12}?)(?:工作|上班|居住|生活)|(?:现在)?住在(.{1,12}))")
_MOVE = re.compile(r"(?:我)?(?:最近|现在|已经)?搬到(.{1,12}?)了")
_SPICE_CHANGE = re.compile(
    r"(?:我)?(?:(?:最近)?开始(?:能|可以)吃(?:点|一点)?辣了|现在(?:不|能|可以)吃(?:点|一点)?辣了)"
)
_CHANGE = re.compile(r"换工作了|转岗|转行|改为|改成|变成|不再|现在不|结婚了|离婚了|分手了|复合了|开始")
_DURABLE = ("employer", "job_role", "relationship_status", "sleep_schedule")
_DOMAIN_CHANGE = {
    "employer": r"换工作了|入职|就职|工作单位.{0,8}(?:改|换|变)",
    "job_role": r"转岗|转行|岗位.{0,8}(?:改|换|变)|改为|改成",
    "relationship_status": r"结婚了|离婚了|分手了|复合了|不再|现在不|开始",
    "sleep_schedule": r"改为|改成|不再|现在不|开始",
}


def _assertion(text: str) -> str | None:
    if not isinstance(text, str) or not 1 <= len(text) <= 200:
        return None
    if _UNSAFE.search(text) or has_optout(text) or mask_quoted(text) != text:
        return None
    return text.strip().rstrip("。.!！")


def stated_city(text: str) -> str | None:
    assertion = _assertion(text)
    match = _CITY.fullmatch(assertion) if assertion else None
    return (match[1] or match[2]) if match else None


def explicit_replacement_slot(previous: str, incoming: str) -> str | None:
    """No model hint, date invention or general semantic similarity is admitted.

    R14 explicitly authorizes a self-reported relocation to replace the unique
    previous city, including the old 'work in city' wording in KU01. Other
    ambiguities remain for the existing confirmation path.
    """
    before, after = _assertion(previous), _assertion(incoming)
    if before is None or after is None:
        return None
    results = {
        slot
        for prior in re.split(r"[，,。；;\n]", before)
        for current in re.split(r"[，,。；;\n]", after)
        if (slot := _replacement(prior.strip(), current.strip(), after))
    }
    return next(iter(results)) if len(results) == 1 else None


def _replacement(before: str, after: str, whole: str) -> str | None:
    if not before or not after or before == after:
        return None
    city, moved = _CITY.fullmatch(before), _MOVE.fullmatch(after)
    if city and moved and moved[1] != (city[1] or city[2]):
        return "residence_city"
    if _SPICE_CHANGE.fullmatch(after) and before.startswith("我") and compatible_statement("spice_preference", before):
        return "spice_preference"
    self_clause = re.match(r"^(?:我|最近|现在|以前)", after) or (
        whole.startswith("我") and re.match(r"^(?:改为|改成|不再|转岗|转行)", after)
    )
    if not before.startswith("我") or not self_clause:
        return None
    changed = _CHANGE.search(whole) or re.search(r"以前.+现在", whole)
    if not changed:
        return None
    matches = [
        slot
        for slot in _DURABLE
        if all(compatible_statement(slot, text) for text in (before, after)) and re.search(_DOMAIN_CHANGE[slot], after)
    ]
    if len(matches) == 1:
        return matches[0]
    from mingjing_core.memory2.conflict_candidates import opposing_preferences

    prior = re.sub(r"^我以前", "我", before)
    current = "我" + after if after.startswith(("现在", "最近")) else after
    explicit_preference = re.search(r"不再|现在不|以前.+现在", after) or (
        re.search(r"以前.+现在", whole) and after.startswith(("现在", "我现在"))
    )
    return "preference" if explicit_preference and opposing_preferences(prior, current) else None

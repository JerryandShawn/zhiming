"""Finite model-supplied slot vocabulary; clues validate rather than infer a slot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


@dataclass(frozen=True)
class Slot:
    name: str
    label: str
    cardinality: Literal["single", "multi"]
    clues: str
    counterexamples: tuple[str, ...]


_TEMPORARY = re.compile(r"出差|旅游|旅行|探亲|路过|暂住|借住|临时|短期|客串|实习体验|代班|代岗|试吃|体验一天")
_SLOTS = (
    Slot("residence_city", "居住城市", "single", r"住在|居住|搬到|定居", ("下周在上海出差", "在北京旅游一周")),
    Slot(
        "employer",
        "工作单位",
        "single",
        r"入职|就职|任职于|工作单位|在.{1,24}(?:公司|集团|单位)工作",
        ("到客户公司出差",),
    ),
    Slot(
        "job_role",
        "职业/岗位",
        "single",
        r"岗位|职业|担任|任职|转岗|转行|做.{0,8}(?:工程师|教师|设计师)",
        ("临时代岗",),
    ),
    Slot("relationship_status", "感情状态", "single", r"单身|恋爱|结婚|已婚|离婚|分手|复合", ("假设我结婚了",)),
    Slot("spice_preference", "饮食偏好·辣", "single", r"吃.{0,8}辣|口味.{0,8}辣|不沾辣", ("今天临时试吃辣椒",)),
    Slot("sleep_schedule", "作息", "single", r"作息|起床|睡觉|入睡|早睡|晚睡|早起|夜班|白班", ("明天临时代夜班",)),
    Slot("exam_goal", "备考目标", "single", r"备考|考研|考公|考试目标|准备考|报考", ("临时体验一天备考班",)),
    Slot("preferred_name", "称呼", "single", r"叫我|称呼我|称呼改为|称呼是", ("临时叫我队长",)),
    Slot("important_people", "重要的人", "multi", r"朋友|同事|家人|妈妈|爸爸|父亲|母亲|伴侣", ("虚构人物",)),
    Slot("hobbies", "爱好", "multi", r"喜欢|爱好|热爱|兴趣", ("仅仅路过球场",)),
)
SLOTS = MappingProxyType({slot.name: slot for slot in _SLOTS})
_LABELS = {slot.label: slot.name for slot in _SLOTS}


def normalize_slot(value: object) -> str | None:
    """Unknown identifiers are omitted, never guessed from a user sentence."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value in SLOTS else _LABELS.get(value)


def compatible_statement(slot: str, quote: str) -> bool:
    """Conservative guard against attaching transient states to enduring slots."""
    canonical = normalize_slot(slot)
    if canonical is None or not isinstance(quote, str) or not quote:
        return False
    if _TEMPORARY.search(quote) or re.search(r"假如|假设|如果|比如|举例|[?？]", quote):
        return False
    return re.search(SLOTS[canonical].clues, quote) is not None

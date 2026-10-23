"""Small explicit slot registry: unknown labels and short trips never overwrite."""

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SlotDefinition:
    name: str
    cardinality: Literal["single", "multi"]
    aliases: tuple[str, ...]


SLOT_DEFINITIONS = (
    SlotDefinition("residence_city", "single", ("现居城市", "居住城市", "常住城市")),
    SlotDefinition("employer", "single", ("当前公司", "雇主", "工作单位")),
    SlotDefinition("occupation", "single", ("当前职业", "职业")),
    SlotDefinition("relationship_status", "single", ("感情状态", "婚姻状态")),
    SlotDefinition("preferred_name", "single", ("称呼偏好", "希望称呼")),
    SlotDefinition("food_spicy", "single", ("辣度偏好", "吃辣偏好")),
    SlotDefinition("sleep_routine", "single", ("作息", "睡眠习惯")),
    SlotDefinition("study_goal", "single", ("当前学习目标", "学习目标")),
    SlotDefinition("current_school", "single", ("当前学校", "就读学校")),
    SlotDefinition("communication_style", "single", ("沟通偏好", "回答风格")),
    SlotDefinition("important_people", "multi", ("重要的人", "重要人物")),
    SlotDefinition("hobbies", "multi", ("爱好", "兴趣爱好")),
)
SLOTS = {definition.name: definition for definition in SLOT_DEFINITIONS}
_ALIASES = {alias: definition.name for definition in SLOT_DEFINITIONS for alias in definition.aliases}
_TEMPORARY = re.compile(
    r"出差|旅游|旅行|探亲|短住|暂住|临时|暂时|过夜|中转|路过|借住|度假|实习.{0,8}(?:天|周|个月)"
    r"|(?:待|住|停留).{0,8}(?:[一二两三四五六七八九十\d]+[天晚]|[一二两三四\d]+周|几天|几周)"
)
_RESIDENCE = re.compile(r"常住|定居|长住|长期.{0,4}住|居住|住在|现居|现住|搬到|搬去|搬来|迁居|我.{0,4}住")
_NOT_CURRENT = re.compile(r"以前|曾经|原来|过去|之前|从前|不(?:再)?住|不(?:在|再)?居住|没(?:有)?住|从未住|未搬")
_OTHER = re.compile(r"朋友|同事|室友|亲戚|爸爸|妈妈|父亲|母亲|他|她")


def normalize_slot(name: str | None, text: str = "") -> str | None:
    if not isinstance(name, str):
        return None
    canonical = name if name in SLOTS else _ALIASES.get(name)
    if canonical == "residence_city" and text and (is_temporary(text) or not _RESIDENCE.search(text)):
        return None
    return canonical


def is_temporary(text: str) -> bool:
    return bool(_TEMPORARY.search(text))


def get_slot(name: str | None, text: str = "") -> SlotDefinition | None:
    return SLOTS.get(normalize_slot(name, text))


def residence_value_asserted(text: str, value: str | None) -> bool:
    if not value or _OTHER.search(text):
        return False
    for clause in re.split(r"[，,。；;\n]", text):
        if _NOT_CURRENT.search(clause) or is_temporary(clause):
            continue
        relation = r"(?:住(?:在)?|定居(?:在)?|现居(?:在)?|搬到|搬去|搬来|迁居).{0,4}"
        if re.search(relation + re.escape(value), clause):
            return True
    return False

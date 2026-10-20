"""Audited program fallback; availability failures never leave a crisis reply empty."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from mingjing_core.domain.contracts import EvidenceError

FALLBACK_TEXT = (
    "我在这儿，听到你说的了。你现在安全吗？\n"
    "如果你有伤害自己的念头，请现在就拨打全国心理援助热线 {hotline}；"
    "如果有紧急危险，马上打 {emergency_joined}。\n"
    "也请联系一个你信任的人，让他现在陪着你。我会一直在这儿陪你说话。"
)
PATTERNS = (
    r"(?:我|自己)(?:现在|今晚|马上|真的|已经|就|也|又|实在|可能|今天|一会儿|最近)*"
    r"(?:想死|不想活|活不下去|(?:想|要|打算|准备|决定)(?:去|要|就|马上|现在)*"
    r"(?:结束生命|自杀|伤害自己|轻生|跳楼|割腕|杀人|杀了他|杀了她|伤害别人))",
)


def crisis_detected(text: str) -> bool:
    if not isinstance(text, str):
        return False
    # Match first-person intent, not a subject mentioned earlier in a long clause.
    # Quoted/academic text still needs model judgment; this conservative program
    # trigger does not classify all possible crisis language.
    return any(re.search(pattern, text) for pattern in PATTERNS)


def fallback_text() -> str:
    path = Path(__file__).resolve().parents[2] / "config/crisis.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if value != {"hotline": "12356", "emergency": ["120", "110"], "fallback_text": FALLBACK_TEXT}:
        raise EvidenceError("危机兜底配置未通过固定模板核验")
    return value["fallback_text"].format(hotline=value["hotline"], emergency_joined=" 或 ".join(value["emergency"]))

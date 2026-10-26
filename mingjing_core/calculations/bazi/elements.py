"""Independent five-element and polarity arithmetic, with explicit provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ELEMENTS = "木火土金水"
PILLARS = ("year", "month", "day", "hour")
HIDDEN = dict(
    zip(
        BRANCHES,
        ("癸", "己癸辛", "甲丙戊", "乙", "戊乙癸", "丙戊庚", "丁己", "己丁乙", "庚壬戊", "辛", "戊辛丁", "壬甲"),
        strict=True,
    )
)
RELATIONS = (("比肩", "劫财"), ("食神", "伤官"), ("偏财", "正财"), ("七杀", "正官"), ("偏印", "正印"))
LIMIT = "传统符号规则与项目诊断分数；不是现实事件预测，也没有科学效度或专家认证"
KNOWLEDGE = Path(__file__).resolve().parents[2] / "knowledge" / "p8_bazi"


def table(name: str) -> dict[str, Any]:
    return json.loads((KNOWLEDGE / (name + ".json")).read_text(encoding="utf-8"))


def element(stem: str) -> str:
    if len(stem) != 1 or stem not in STEMS:
        raise ValueError("天干无效")
    return ELEMENTS[STEMS.index(stem) // 2]


def ten_god(master: str, other: str) -> str:
    """Derive all 100 relations without importing the calendar engine's table."""
    element(master)
    element(other)
    left, right = STEMS.index(master), STEMS.index(other)
    return RELATIONS[(right // 2 - left // 2) % 5][int(left % 2 != right % 2)]


def block(method: str, source: str, **data: Any) -> dict[str, Any]:
    return {"method": method, "school": "p8-explicit-multimethod-v1", "source": source, "limits": [LIMIT], **data}


def validate_pillars(pillars: dict[str, str]) -> None:
    if set(pillars) != set(PILLARS):
        raise ValueError("需要完整四柱")
    for value in pillars.values():
        if len(value) != 2 or value[0] not in STEMS or value[1] not in BRANCHES:
            raise ValueError("四柱干支无效")
        if STEMS.index(value[0]) % 2 != BRANCHES.index(value[1]) % 2:
            raise ValueError("干支阴阳配对无效")


def ten_gods(pillars: dict[str, str]) -> dict[str, Any]:
    master = pillars["day"][0]
    rows = {}
    for name, value in pillars.items():
        hidden = HIDDEN[value[1]]
        # Roles are this project's positional labeling, not a universal qi ratio.
        roles = ("本气", "余气") if len(hidden) == 2 else ("本气", "中气", "余气")
        rows[name] = {
            "exposed": {"stem": value[0], "ten_god": ten_god(master, value[0])},
            "hidden": [
                {"stem": stem, "role": roles[index], "ten_god": ten_god(master, stem)}
                for index, stem in enumerate(hidden)
            ],
        }
    return block(
        "p8-five-element-polarity-v1",
        "三命通会·论五行生克；藏干沿用v3表",
        day_master=master,
        pillars=rows,
        complete_table={stem: ten_god(master, stem) for stem in STEMS},
        role_note="二藏干第二项标余气；三藏干按既有表顺序标中/余，属项目标注口径；不是气量",
    )


def relations(left: str, right: str) -> list[str]:
    result = []
    pair = frozenset((left[1], right[1]))
    if pair in [frozenset(p) for p in ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥")]:
        result.append("地支六冲")
    if pair in [frozenset(p) for p in ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")]:
        result.append("地支六合")
    if abs(STEMS.index(left[0]) - STEMS.index(right[0])) == 5:
        result.append("天干五合")
    return result


def relative_pillar(ganzhi: str, master: str, natal: dict[str, str]) -> dict[str, Any]:
    return {
        "ganzhi": ganzhi,
        "stem_ten_god": ten_god(master, ganzhi[0]),
        "hidden_ten_gods": [{"stem": stem, "ten_god": ten_god(master, stem)} for stem in HIDDEN[ganzhi[1]]],
        "natal_relations": [
            {"pillar": name, "natal_ganzhi": value, "relations": relations(ganzhi, value)}
            for name, value in natal.items()
        ],
        "transformation_established": False,
    }

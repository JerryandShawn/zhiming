"""Conditional pattern screens and distinct useful-element proposals."""

from __future__ import annotations

from typing import Any

from .elements import HIDDEN, STEMS, block, element, table, ten_god
from .strength import supportive

GODS = ("正官", "七杀", "正印", "偏印", "正财", "偏财", "食神", "伤官")
PATTERN_SUPPORT = {
    "正官": ("正财", "正印"),
    "七杀": ("食神",),
    "正印": ("正官",),
    "偏印": ("正财",),
    "正财": ("食神", "正官"),
    "偏财": ("食神", "正官"),
    "食神": ("偏财",),
    "伤官": ("正印", "正财"),
}
AVOID = {
    "正官": "伤官",
    "七杀": "正财",
    "正印": "正财",
    "偏印": "偏财",
    "正财": "劫财",
    "偏财": "比肩",
    "食神": "偏印",
    "伤官": "七杀",
}


def conditions(rows: list[tuple[str, bool, Any]]) -> dict[str, Any]:
    facts = [{"condition": name, "satisfied": bool(value), "evidence": evidence} for name, value, evidence in rows]
    return {
        "conditions": facts,
        "satisfied": [row["condition"] for row in facts if row["satisfied"]],
        "unsatisfied": [row["condition"] for row in facts if not row["satisfied"]],
        "screen_passed": all(row["satisfied"] for row in facts),
    }


def regular_patterns(month_gods: set[str], exposed: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "pattern": god + "格",
            "ten_god": god,
            **conditions(
                [
                    ("月支藏该十神", god in month_gods, sorted(month_gods)),
                    ("年月时透该十神", god in exposed, exposed),
                    (
                        "年月时未见本筛选的直接牵制神",
                        AVOID[god] not in exposed,
                        {"screened_god": AVOID[god], "exposed": exposed},
                    ),
                ]
            ),
        }
        for god in GODS
    ]


def following_patterns(
    pillars: dict[str, str], methods: list[dict[str, Any]], month_gods: set[str], exposed: list[str], hidden: list[str]
) -> list[dict[str, Any]]:
    master = pillars["day"][0]
    no_root = all(element(stem) != element(master) for value in pillars.values() for stem in HIDDEN[value[1]])
    no_help = all(not supportive(master, value[0]) for name, value in pillars.items() if name != "day")
    weak = all(row["score"] <= 20 for row in methods)
    follow = []
    for name, gods in (("从财", ("正财", "偏财")), ("从杀", ("正官", "七杀")), ("从儿", ("食神", "伤官"))):
        group = [god for god in hidden + exposed if god in gods]
        follow.append(
            {
                "pattern": name,
                **conditions(
                    [
                        ("日主无同五行根", no_root, hidden),
                        ("年月时无印比生扶", no_help, exposed),
                        ("两种诊断分均不高于20", weak, [row["score"] for row in methods]),
                        ("该类十神至少占透藏非日干的一半", len(group) * 2 >= len(hidden + exposed), group),
                        ("月令含该类十神", bool(month_gods.intersection(gods)), sorted(month_gods)),
                    ]
                ),
            }
        )
    follow.append(strong_following(pillars, methods, exposed, hidden))
    return follow


def strong_following(
    pillars: dict[str, str], methods: list[dict[str, Any]], exposed: list[str], hidden: list[str]
) -> dict[str, Any]:
    master = pillars["day"][0]
    return {
        "pattern": "从旺",
        **conditions(
            [
                (
                    "年月时全为印比",
                    all(supportive(master, value[0]) for name, value in pillars.items() if name != "day"),
                    exposed,
                ),
                (
                    "四支本气全为印比",
                    all(supportive(master, HIDDEN[value[1]][0]) for value in pillars.values()),
                    hidden,
                ),
                (
                    "两种诊断分均不低于80",
                    all(row["score"] >= 80 for row in methods),
                    [row["score"] for row in methods],
                ),
            ]
        ),
    }


def patterns(pillars: dict[str, str], strength: dict[str, Any]) -> dict[str, Any]:
    master = pillars["day"][0]
    month_gods = {ten_god(master, stem) for stem in HIDDEN[pillars["month"][1]]}
    exposed = [ten_god(master, value[0]) for name, value in pillars.items() if name != "day"]
    hidden = [ten_god(master, stem) for value in pillars.values() for stem in HIDDEN[value[1]]]
    return block(
        "p8-pattern-condition-screen-v1",
        "子平真诠·论用神/论用神变化；项目条件筛选非完整成格法",
        editorial_status="original_editorial_unreviewed",
        regular_eight=regular_patterns(month_gods, exposed),
        following=following_patterns(pillars, strength["methods"], month_gods, exposed, hidden),
        establishment="candidate_only",
        not_evaluated=["合化成立", "救应力量", "特殊外格", "真假从格", "岁运成败"],
        warnings=["未过筛选不等于排除该流派格局；过筛也不宣称成格；候选可并存"],
    )


def climate(master: str, month: str) -> dict[str, Any]:
    knowledge = table("climate")
    row = knowledge["rows"][master + month]
    public = {key: value for key, value in row.items() if key != "source_excerpt"}
    return block(
        knowledge["method"],
        knowledge["source"],
        day_master=master,
        month_branch=month,
        table_version=knowledge["version"],
        editorial_status=knowledge["editorial_status"],
        **public,
        table_limits=knowledge["limitations"],
        warnings=["原典开篇/季节摘表的候选，不执行全篇例外；不是气象数据或医学结论；排序不等于适用于全盘"],
    )


def useful(
    pillars: dict[str, str], strength: dict[str, Any], pattern: dict[str, Any], climatic: dict[str, Any]
) -> dict[str, Any]:
    master = pillars["day"][0]
    balancing = []
    for method in strength["methods"]:
        label = method["conclusion"]
        stems = [stem for stem in STEMS if supportive(master, stem) == (label == "偏弱")] if label != "中间区间" else []
        balancing.append(
            {
                "strength_method": method["method"],
                "conclusion": label,
                "candidate_stems": stems,
                "status": "candidate" if stems else "no_direction_in_middle_band",
            }
        )
    structural = []
    for row in pattern["regular_eight"]:
        if row["conditions"][0]["satisfied"]:
            gods = PATTERN_SUPPORT[row["ten_god"]]
            structural.append(
                {
                    "pattern": row["pattern"],
                    "pattern_screen_passed": row["screen_passed"],
                    "candidate_ten_gods": list(gods),
                    "candidate_stems": [stem for stem in STEMS if ten_god(master, stem) in gods],
                }
            )
    sets = {
        "扶抑": {stem for row in balancing for stem in row["candidate_stems"]},
        "调候": set(climatic["candidate_stems"]),
        "格局": {stem for row in structural for stem in row["candidate_stems"]},
    }
    intersection = set.intersection(*sets.values())
    return block(
        "p8-three-useful-proposals-v1",
        "扶抑为项目诊断；调候为版本化摘表；格局参子平真诠顺逆用概念",
        balancing=balancing,
        climate={"candidate_stems": climatic["candidate_stems"], "source_locator": climatic["source_locator"]},
        pattern=structural,
        consensus_stems=sorted(intersection, key=STEMS.index),
        disagreements={key: sorted(values - intersection, key=STEMS.index) for key, values in sets.items()},
        comparison_scope="候选天干集合交集，不按票数裁定喜用；扶抑自身分歧保留",
        warnings=["不使用五行缺什么补什么，不据此给职业/健康/投资保证；完整取用须复核合冲与流派例外"],
    )

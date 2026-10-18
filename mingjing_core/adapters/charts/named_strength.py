"""Project-v1 diagnostic weights applied to the explicitly selected hidden map."""

from __future__ import annotations

from typing import Any

from ...calculations.bazi.elements import block, element, ten_god
from ...calculations.bazi.strength import PARAMETERS, conclusion, supportive
from ...calculations.bazi.structure import conditions, regular_patterns


def named_scores(pillars: dict[str, str], hidden: dict[str, str]) -> dict[str, Any]:
    master = pillars["day"][0]
    roots = []
    for name, value in pillars.items():
        stems = hidden[value[1]]
        weights = [1] if len(stems) == 1 else [0.7, 0.3] if len(stems) == 2 else [0.6, 0.3, 0.1]
        amount = sum(weight for stem, weight in zip(stems, weights, strict=True) if element(stem) == element(master))
        roots.append(
            {"pillar": name, "same_element_root_fraction": round(amount, 6), "contribution": round(amount * 10, 6)}
        )
    exposed = [
        {"pillar": key, "stem": value[0], "supports": supportive(master, value[0])}
        for key, value in pillars.items()
        if key != "day"
    ]
    order = supportive(master, hidden[pillars["month"][1]][0])
    ground = [key for key, value in pillars.items() if supportive(master, hidden[value[1]][0])]
    momentum = [row["pillar"] for row in exposed if row["supports"]]
    a = round(40 * order + sum(row["contribution"] for row in roots) + len(momentum) * (20 / 3), 6)
    axes = {
        "得令": {"value": order, "score": int(order) * 40},
        "得地": {"supportive_branches": ground, "score": len(ground) * 7.5},
        "得势": {"supportive_exposed": momentum, "score": len(momentum) * 10},
    }
    b = sum(row["score"] for row in axes.values())
    return block(
        "p8-two-editorial-strength-v1",
        "项目口径v1；旺相等术语参三命通会卷二，数值非古法原文",
        editorial_status="project_method_v1_accepted_not_empirical_validity",
        methods=[
            {
                "method": "p8-month-root-exposed-v1",
                "parameters": dict(PARAMETERS),
                "score": a,
                "conclusion": conclusion(a, 45, 55),
                "month_support": order,
                "roots": roots,
                "exposed": exposed,
            },
            {
                "method": "p8-order-ground-momentum-v1",
                "parameters": {"axes_max": [40, 30, 30], "lower": 45, "upper": 55},
                "score": b,
                "conclusion": conclusion(b, 45, 55),
                "axes": axes,
            },
        ],
        agreement=conclusion(a, 45, 55) == conclusion(b, 45, 55),
        hidden_stems_used=hidden,
        warning="项目自定权重与45/55阈值；两法并列，不合并唯一结论；不处理合化/燥湿减力",
    )


def named_patterns(pillars: dict[str, str], hidden: dict[str, str], strength: dict[str, Any]) -> dict[str, Any]:
    master = pillars["day"][0]
    month_gods = {ten_god(master, stem) for stem in hidden[pillars["month"][1]]}
    exposed = [ten_god(master, value[0]) for key, value in pillars.items() if key != "day"]
    concealed = [ten_god(master, stem) for value in pillars.values() for stem in hidden[value[1]]]
    methods, following = strength["methods"], []
    for name, gods in (("从财", ("正财", "偏财")), ("从杀", ("正官", "七杀")), ("从儿", ("食神", "伤官"))):
        group = [god for god in concealed + exposed if god in gods]
        following.append(
            {
                "pattern": name,
                **conditions(
                    [
                        (
                            "日主无同五行根",
                            all(
                                element(stem) != element(master)
                                for value in pillars.values()
                                for stem in hidden[value[1]]
                            ),
                            concealed,
                        ),
                        (
                            "年月时无印比生扶",
                            all(not supportive(master, value[0]) for key, value in pillars.items() if key != "day"),
                            exposed,
                        ),
                        (
                            "两种诊断分均不高于20",
                            all(row["score"] <= 20 for row in methods),
                            [row["score"] for row in methods],
                        ),
                        ("该类十神至少占透藏非日干的一半", len(group) * 2 >= len(concealed + exposed), group),
                        ("月令含该类十神", bool(month_gods.intersection(gods)), sorted(month_gods)),
                    ]
                ),
            }
        )
    following.append(_strong_following(pillars, hidden, methods, exposed, concealed))
    return block(
        "p8-pattern-condition-screen-v1",
        "子平真诠·论用神/变化；项目候选筛选，不宣称成格",
        editorial_status="project_candidate_screen",
        regular_eight=regular_patterns(month_gods, exposed),
        following=following,
        establishment="candidate_only",
        not_evaluated=["合化成立", "救应力量", "特殊外格", "真假从格", "岁运成败"],
        warnings=["过筛不等于成格；救应合化待正式阶段；采用显式选择的藏干表"],
    )


def _strong_following(
    pillars: dict[str, str],
    hidden: dict[str, str],
    methods: list[dict[str, Any]],
    exposed: list[str],
    concealed: list[str],
) -> dict[str, Any]:
    master = pillars["day"][0]
    return {
        "pattern": "从旺",
        **conditions(
            [
                (
                    "年月时全为印比",
                    all(supportive(master, value[0]) for key, value in pillars.items() if key != "day"),
                    exposed,
                ),
                (
                    "四支本气全为印比",
                    all(supportive(master, hidden[value[1]][0]) for value in pillars.values()),
                    concealed,
                ),
                ("两种诊断分均不低于80", all(row["score"] >= 80 for row in methods), [row["score"] for row in methods]),
            ]
        ),
    }

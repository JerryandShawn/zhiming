"""Two transparent editorial diagnostic scores; neither is an orthodox truth."""

from __future__ import annotations

from typing import Any

from .elements import ELEMENTS, HIDDEN, block, element


def supportive(master: str, stem: str) -> bool:
    return (ELEMENTS.index(element(stem)) - ELEMENTS.index(element(master))) % 5 in (0, 4)


def conclusion(score: float, lower: float, upper: float) -> str:
    return "偏弱" if score < lower else "偏强" if score > upper else "中间区间"


PARAMETERS = {
    "month_weight": 40,
    "root_weight_per_branch": 10,
    "exposed_weight_per_stem": 20 / 3,
    "hidden_weights": [0.6, 0.3, 0.1],
    "two_hidden_weights": [0.7, 0.3],
    "lower": 45,
    "upper": 55,
}


def root_contributions(pillars: dict[str, str]) -> list[dict[str, Any]]:
    master = pillars["day"][0]
    roots = []
    for name, value in pillars.items():
        hidden = HIDDEN[value[1]]
        weights = (
            [1]
            if len(hidden) == 1
            else PARAMETERS["two_hidden_weights"]
            if len(hidden) == 2
            else PARAMETERS["hidden_weights"]
        )
        amount = sum(weight for stem, weight in zip(hidden, weights, strict=True) if element(stem) == element(master))
        roots.append(
            {"pillar": name, "same_element_root_fraction": round(amount, 6), "contribution": round(amount * 10, 6)}
        )
    return roots


def axis_scores(pillars: dict[str, str], exposed: list[dict[str, Any]]) -> dict[str, Any]:
    master, month = pillars["day"][0], pillars["month"][1]
    month_support = supportive(master, HIDDEN[month][0])
    axes = {
        "得令": {"value": month_support, "score": int(month_support) * 40},
        "得地": {
            "supportive_branches": [name for name, value in pillars.items() if supportive(master, HIDDEN[value[1]][0])]
        },
        "得势": {"supportive_exposed": [row["pillar"] for row in exposed if row["supports"]]},
    }
    axes["得地"]["score"] = len(axes["得地"]["supportive_branches"]) * 7.5
    axes["得势"]["score"] = len(axes["得势"]["supportive_exposed"]) * 10
    return axes


def scores(pillars: dict[str, str]) -> dict[str, Any]:
    master, month = pillars["day"][0], pillars["month"][1]
    month_support = supportive(master, HIDDEN[month][0])
    roots = root_contributions(pillars)
    exposed = [
        {"pillar": name, "stem": value[0], "supports": supportive(master, value[0])}
        for name, value in pillars.items()
        if name != "day"
    ]
    a = round(
        40 * month_support
        + sum(row["contribution"] for row in roots)
        + sum(row["supports"] for row in exposed) * (20 / 3),
        6,
    )
    # Method B ignores partial qi fractions and measures three independent axes.
    axes = axis_scores(pillars, exposed)
    b = sum(row["score"] for row in axes.values())
    return block(
        "p8-two-editorial-strength-v1",
        "三命通会卷二·旺相休囚死仅作概念来源，数值非原典",
        editorial_status="original_editorial_unreviewed",
        methods=[
            {
                "method": "p8-month-root-exposed-v1",
                "parameters": dict(PARAMETERS),
                "score": a,
                "conclusion": conclusion(a, 45, 55),
                "month_support": month_support,
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
        warning="两个诊断值均未做专家标定，不合并成唯一结论；忽略合化、刑冲减力与燥湿等条件",
    )

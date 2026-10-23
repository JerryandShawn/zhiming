"""Reviewed P8 candidate screens; the legacy structure calculator stays frozen."""

from __future__ import annotations

from typing import Any

from ...calculations.bazi.elements import STEMS, ten_god
from ...calculations.bazi.structure import GODS, PATTERN_SUPPORT, conditions
from ...calculations.bazi.structure import useful as legacy_useful

SUPPORT = dict(PATTERN_SUPPORT, 七杀=("食神", "正印", "偏印"))
LU = dict(zip(STEMS, "寅卯巳午巳午申酉亥子", strict=True))
YANG_BLADE = dict(zip("甲丙戊庚壬", "卯午午酉子", strict=True))
MIXED_NOTE = "辰戌丑未为杂气月；第十六章透干会支取用尚未完整实现，不能据候选宣布成格"


def restraint(god: str, exposed: list[str], master: str) -> dict[str, Any]:
    present = set(exposed)
    wealth = bool(present.intersection(("正财", "偏财")))
    peers = bool(present.intersection(("比肩", "劫财")))
    checks = {
        "正官": {"伤官透出": "伤官" in present},
        "七杀": {"财星透出且无食神透出": wealth and "食神" not in present},
        "正印": {"财星透出": wealth},
        "偏印": {"财星透出": wealth},
        "正财": {"比劫透出": peers, "七杀透出": "七杀" in present},
        "偏财": {"比劫透出": peers, "七杀透出": "七杀" in present},
        "食神": {"偏印透出": "偏印" in present},
        "伤官": {"非庚辛日主且正官透出": master not in "庚辛" and "正官" in present},
    }[god]
    untested = {
        "七杀": ["食神制杀力量、身强及财食先后未判；有食神透出仅解除本条显性筛选"],
        "正印": ["印轻前提未判；身强印重透杀及印多用财救应未判"],
        "偏印": ["印轻前提未判；身强印重透杀及印多用财救应未判"],
        "正财": ["财轻比重前提未判；食神化劫、合杀等救应未判"],
        "偏财": ["财轻比重前提未判；食神化劫、合杀等救应未判"],
        "食神": ["生财露杀及救应未判"],
        "伤官": ["庚辛例外按24号裁定；财印辅助、季节及伤官官星并透等专章限制未判"],
    }.get(god, ["刑冲、合化与印星救应未判"])
    return {
        "checks": checks,
        "blocked": any(checks.values()),
        "exposed": exposed,
        "day_master": master,
        "metal_water_exception": god == "伤官" and master in "庚辛",
        "not_evaluated": untested,
    }


def reviewed_regular(pillars: dict[str, str], hidden: dict[str, str]) -> list[dict[str, Any]]:
    master, month = pillars["day"][0], pillars["month"][1]
    stems = hidden[month]
    roles = ("本气", "余气") if len(stems) == 2 else ("本气", "中气", "余气")
    month_rows = [
        {"stem": stem, "ten_god": ten_god(master, stem), "qi_rank": i, "role": roles[i]} for i, stem in enumerate(stems)
    ]
    exposed = [ten_god(master, value[0]) for key, value in pillars.items() if key != "day"]
    rows = []
    for god in GODS:
        matches = [row for row in month_rows if row["ten_god"] == god]
        screening = restraint(god, exposed, master)
        rows.append(
            {
                "pattern": god + "格",
                "ten_god": god,
                "notes": [MIXED_NOTE] if month in "辰戌丑未" else [],
                **conditions(
                    [
                        ("月支藏该十神", bool(matches), {"matches": matches, "month_branch": month}),
                        ("年月时透该十神", god in exposed, exposed),
                        ("未见本筛选的显性牵制条件", not screening["blocked"], screening),
                    ]
                ),
            }
        )
    return rows


def _lu_pathways(present: set[str]) -> dict[str, bool]:
    wealth = bool(present.intersection(("正财", "偏财")))
    seal = bool(present.intersection(("正印", "偏印")))
    return {
        "透官逢财或印": "正官" in present and (wealth or seal),
        "透财逢食伤": wealth and bool(present.intersection(("食神", "伤官"))),
        "透杀逢食神候选制伏": "七杀" in present and "食神" in present,
    }


def reviewed_extra(pillars: dict[str, str], hidden: dict[str, str]) -> list[dict[str, Any]]:
    master, month = pillars["day"][0], pillars["month"][1]
    main_god = ten_god(master, hidden[month][0])
    exposed = [ten_god(master, value[0]) for key, value in pillars.items() if key != "day"]
    present, rows = set(exposed), []
    pathways = _lu_pathways(present)
    bad_lu = not present.intersection(("正财", "偏财", "正官")) and "七杀" in present
    bad_lu = bool(bad_lu and present.intersection(("正印", "偏印")))
    for name in ("建禄", "月劫", "阳刃"):
        blade = name == "阳刃"
        anchor = month == LU[master] if name == "建禄" else master not in YANG_BLADE and main_god == "劫财"
        anchor = month == YANG_BLADE.get(master) if blade else anchor
        support = bool(present.intersection(("正财", "偏财", "正印", "偏印")))
        route = bool(present.intersection(("正官", "七杀"))) and support if blade else any(pathways.values())
        rows.append(
            {
                "pattern": name + "格",
                "notes": ["三项是项目显性候选筛选；根气强弱、制伏有效、合去官杀与救应均未判"],
                **conditions(
                    [
                        ("月令符合具名格局锚点", anchor, {"day_master": master, "month": month}),
                        ("透干满足一条候选取用路径", route, {"exposed": exposed, "lu_pathways": pathways}),
                        ("未见本条显性败因", "伤官" not in present if blade else not bad_lu, exposed),
                    ]
                ),
            }
        )
    return rows


def reviewed_useful(
    pillars: dict[str, str], strength: dict[str, Any], pattern: dict[str, Any], climatic: dict[str, Any]
) -> dict[str, Any]:
    result = legacy_useful(pillars, strength, pattern, climatic)
    for row in result["pattern"]:
        god = row["pattern"].removesuffix("格")
        row["candidate_ten_gods"] = list(SUPPORT[god])
        row["candidate_stems"] = [stem for stem in STEMS if ten_god(pillars["day"][0], stem) in SUPPORT[god]]
    sets = {
        "扶抑": {stem for row in result["balancing"] for stem in row["candidate_stems"]},
        "调候": set(climatic["candidate_stems"]),
        "格局": {stem for row in result["pattern"] for stem in row["candidate_stems"]},
    }
    intersection = set.intersection(*sets.values())
    result["consensus_stems"] = sorted(intersection, key=STEMS.index)
    result["disagreements"] = {key: sorted(values - intersection, key=STEMS.index) for key, values in sets.items()}
    result["method"] = "p8-three-useful-proposals-v2-reviewed"
    result["pattern_support"] = {god: list(candidates) for god, candidates in SUPPORT.items()}
    result["pattern_support_note"] = "七杀用食或用印为并列候选，不主张同时并用；第三十九章力量与先后条件未判"
    return result

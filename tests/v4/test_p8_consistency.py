"""Independent concrete fact tables cover all six requested assertion domains."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.skills.consistency import check_chart_consistency

ROOT = Path(__file__).resolve().parents[2]
STEMS = "甲乙丙丁戊己庚辛壬癸"
STARS = [
    "紫微",
    "天机",
    "太阳",
    "武曲",
    "天同",
    "廉贞",
    "天府",
    "太阴",
    "贪狼",
    "巨门",
    "天相",
    "天梁",
    "七杀",
    "破军",
]
PALACES = {
    "田宅宫": [],
    "官禄宫": [],
    "仆役宫": ["天同"],
    "迁移宫": ["武曲", "破军"],
    "疾厄宫": ["太阳"],
    "财帛宫": ["天府"],
    "子女宫": ["天机", "太阴"],
    "夫妻宫": ["紫微", "贪狼"],
    "兄弟宫": ["巨门"],
    "命宫": ["天相"],
    "父母宫": ["天梁"],
    "福德宫": ["廉贞", "七杀"],
}
PLANETS = {
    "太阳": ("双鱼", 12, False),
    "月亮": ("双鱼", 12, False),
    "水星": ("水瓶", 11, False),
    "金星": ("白羊", 12, False),
    "火星": ("双鱼", 12, False),
    "木星": ("天蝎", 7, True),
    "土星": ("双鱼", 12, False),
    "天王": ("摩羯", 10, False),
    "海王": ("摩羯", 10, False),
    "冥王": ("天蝎", 8, True),
}


@pytest.fixture(scope="module")
def charts() -> dict:
    return {
        system: json.loads(
            (ROOT / f"docs/v4/contracts/samples/ayuan_{system}.json").read_text(
                encoding="utf8"
            )
        )
        for system in ("bazi", "ziwei", "astro")
    }


def one(answer: str, chart: dict) -> dict:
    result = check_chart_consistency(answer, chart)
    assert len(result["data"]["checks"]) == 1
    return result["data"]["checks"][0]


@pytest.mark.parametrize("stem", list(STEMS))
@pytest.mark.parametrize("negative", [False, True], ids=["affirmed", "negated"])
def test_every_day_stem_compares_actual_day_master_with_direct_negation(
    charts: dict, stem: str, negative: bool
) -> None:
    row = one("你的日主" + ("不是" if negative else "是") + stem, charts["bazi"])
    correct = (stem == "丁") != negative
    assert row["outcome"] == ("matched" if correct else "contradiction")
    assert row["expected_values"] == ["丁"]
    assert row["source_refs"][0]["path"].endswith("/pillars/day/gan")


@pytest.mark.parametrize(
    "pattern",
    ["正官格", "七杀格", "正印格", "偏印格", "正财格", "偏财格", "食神格", "伤官格"],
)
@pytest.mark.parametrize(
    "passed", [True, False], ids=["screen-passed", "screen-failed"]
)
def test_pattern_only_checks_declared_screen_without_claiming_established_pattern(
    charts: dict, pattern: str, passed: bool
) -> None:
    row = one(pattern + "候选筛选" + ("通过" if passed else "未通过"), charts["bazi"])
    assert row["field"] == "pattern_screen"
    assert row["expected_values"] == [pattern == "正印格"]
    assert row["outcome"] == (
        "matched" if (pattern == "正印格") == passed else "contradiction"
    )


@pytest.mark.parametrize("stem", list(STEMS))
@pytest.mark.parametrize(
    "method,expected",
    [
        ("调候", "庚甲"),
        ("扶抑[p8-month-root-exposed-v1]", "戊己庚辛壬癸"),
        ("格局[正印格]", "壬"),
    ],
)
def test_useful_membership_stays_with_explicit_method_and_never_finalizes(
    charts: dict, stem: str, method: str, expected: str
) -> None:
    row = one(method + "候选天干包括" + stem, charts["bazi"])
    assert row["outcome"] == ("matched" if stem in expected else "contradiction")
    assert row["fact_sources"] and row["input_c_aliases"]


@pytest.mark.parametrize(
    "index,ganzhi",
    list(
        enumerate(
            [
                "戊辰",
                "己巳",
                "庚午",
                "辛未",
                "壬申",
                "癸酉",
                "甲戌",
                "乙亥",
                "丙子",
                "丁丑",
            ],
            1,
        )
    ),
)
def test_each_of_ten_nominal_decades_is_addressed_by_explicit_index(
    charts: dict, index: int, ganzhi: str
) -> None:
    row = one(f"第{index}步大运是{ganzhi}", charts["bazi"])
    assert row["outcome"] == "matched" and row["expected_values"] == [ganzhi]
    wrong = "甲子" if ganzhi != "甲子" else "乙丑"
    assert (
        one(f"第{index}步大运是{wrong}", charts["bazi"])["outcome"] == "contradiction"
    )


@pytest.mark.parametrize("palace,actual", PALACES.items())
@pytest.mark.parametrize("star", STARS)
def test_twelve_palaces_by_fourteen_primary_stars_check_actual_placement_not_borrowed_stars(
    charts: dict, palace: str, actual: list[str], star: str
) -> None:
    row = one(palace + "主星包括" + star, charts["ziwei"])
    assert row["outcome"] == ("matched" if star in actual else "contradiction")
    assert row["expected_values"] == [actual]
    assert row["source_refs"][0]["path"].endswith("/major")


@pytest.mark.parametrize("palace,actual", PALACES.items())
def test_empty_palace_is_actual_empty_major_array_not_an_absent_zodiac_sign(
    charts: dict, palace: str, actual: list[str]
) -> None:
    row = one(palace + "是空宫", charts["ziwei"])
    assert row["outcome"] == ("matched" if not actual else "contradiction")


@pytest.mark.parametrize("planet,values", PLANETS.items())
def test_all_ten_natal_planets_have_the_expected_sign_house_and_motion(
    charts: dict, planet: str, values: tuple
) -> None:
    sign, house, retrograde = values
    chart = charts["astro"]
    assert one(f"本命{planet}在{sign}座", chart)["outcome"] == "matched"
    assert one(f"本命{planet}在第{house}宫", chart)["outcome"] == "matched"
    assert (
        one(f"本命{planet}" + ("逆行" if retrograde else "顺行"), chart)["outcome"]
        == "matched"
    )
    wrong_sign = "狮子" if sign != "狮子" else "处女"
    assert one(f"本命{planet}在{wrong_sign}座", chart)["outcome"] == "contradiction"
    wrong_house = house % 12 + 1
    assert one(f"本命{planet}在第{wrong_house}宫", chart)["outcome"] == "contradiction"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("本命太阳在双鱼21度", "matched"),
        ("本命太阳在双鱼21.2度", "matched"),
        ("本命太阳在双鱼21.20度", "matched"),
        ("本命太阳在双鱼21.19654度", "matched"),
        ("本命太阳在双鱼21.1965度", "matched"),
        ("本命太阳在双鱼21.196540度", "matched"),
        ("本命太阳在双鱼21.3度", "contradiction"),
        ("本命太阳在双鱼21.19度", "contradiction"),
        ("本命太阳在双鱼0度", "contradiction"),
        ("本命太阳在双鱼29.999999度", "contradiction"),
        ("本命太阳不在狮子21.2度", "matched"),
        ("本命太阳不在双鱼21.2度", "contradiction"),
        ("本命金星在白羊4.25度", "matched"),
        ("本命金星在白羊4.2度", "matched"),
        ("本命水星在水瓶24.8度", "matched"),
        ("本命木星在天蝎14.45度", "matched"),
        ("本命天王星在摩羯25.33度", "matched"),
        ("本命海王星在摩羯22.82度", "matched"),
        ("本命冥王星在天蝎28.04度", "matched"),
    ],
)
def test_decimal_degrees_obey_written_precision_not_integer_truncation(
    charts: dict, text: str, expected: str
) -> None:
    assert one(text, charts["astro"])["outcome"] == expected


@pytest.mark.parametrize(
    "text",
    [
        "日主是丁。",
        "你的日干为丁火",
        "本盘的日主=丁",
        "此盘日主：丁",
        "阿远的日主是丁",
        "阿远日主是丁",
        "我的日主是丁",
        "日主并非甲",
    ],
)
def test_bounded_subject_and_operator_forms_are_parsed_without_arbitrary_person_matching(
    charts: dict, text: str
) -> None:
    assert (
        check_chart_consistency(text, charts["bazi"])["data"]["status"]
        == "no_contradiction_found"
    )


def test_pure_deterministic_result_does_not_mutate_input_or_copy_freeform_text(
    charts: dict,
) -> None:
    chart = deepcopy(charts["bazi"])
    before = deepcopy(chart)
    text = "私人叙述：工作烦恼。你的日主是甲。"
    result = check_chart_consistency(text, chart)
    assert result == check_chart_consistency(text, chart) and chart == before
    assert "私人叙述" not in json.dumps(result, ensure_ascii=False)
    assert result["data"]["status"] == "inconsistent"
    assert result["effects"]["model_calls"] == result["effects"]["writes"] == 0

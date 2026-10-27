"""Hard-to-interpret language must never become a confident chart contradiction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mingjing_core.skills.consistency import check_chart_consistency

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def bazi() -> dict:
    return json.loads(
        (ROOT / "docs/v4/contracts/samples/ayuan_bazi.json").read_text(encoding="utf8")
    )


@pytest.mark.parametrize(
    "text,reason",
    [
        ("如果日主是甲，正官格候选筛选通过", "hypothetical"),
        ("假如日主是甲", "hypothetical"),
        ("假设日主是甲", "hypothetical"),
        ("倘若日主是甲", "hypothetical"),
        ("若是日主是甲", "hypothetical"),
        ("若日主是甲", "hypothetical"),
        ("即使日主是甲", "hypothetical"),
        ("要是日主是甲", "hypothetical"),
        ("假定日主是甲", "hypothetical"),
        ("设想日主是甲", "hypothetical"),
        ("日主是甲吗？", "question"),
        ("日主是甲?", "question"),
        ("是否日主是甲", "question"),
        ("日主是不是甲", "question"),
        ("难道日主是甲", "question"),
        ("为何日主是甲", "question"),
        ("日主是甲呢", "question"),
        ("怎么日主是甲", "question"),
        ("日主不是不为甲", "complex_negation"),
        ("日主并非不是甲", "complex_negation"),
        ("不能说不是日主甲", "complex_negation"),
        ("日主不一定是甲", "complex_negation"),
        ("日主未必是甲", "complex_negation"),
        ("不排除日主是甲", "complex_negation"),
        ("日主不是甲，而是丁", "complex_negation"),
        ("日主可能是甲", "uncertain"),
        ("日主也许是甲", "uncertain"),
        ("日主大概是甲", "uncertain"),
        ("日主或许是甲", "uncertain"),
        ("日主似乎是甲", "uncertain"),
        ("推测日主是甲", "uncertain"),
        ("日主尚未判断", "uncertain"),
        ("日主未评估", "uncertain"),
        ("日主是甲，仍待核", "uncertain"),
        ("日主未确认", "uncertain"),
        ("北京时间日主是甲", "comparison_basis"),
        ("北京时日主是甲", "comparison_basis"),
        ("钟表时日主是甲", "comparison_basis"),
        ("比较盘日主是甲", "comparison_basis"),
        ("另一口径日主是甲", "comparison_basis"),
        ("他的日主是甲", "other_subject"),
        ("她的日主是甲", "other_subject"),
        ("小禾日主是甲", "other_subject"),
        ("对方日主是甲", "other_subject"),
        ("朋友的日主是甲", "other_subject"),
        ("母亲日主是甲", "other_subject"),
        ("父亲日主是甲", "other_subject"),
        ("妻子日主是甲", "other_subject"),
        ("丈夫日主是甲", "other_subject"),
        ("另一人日主是甲", "other_subject"),
        ("旧盘日主是甲", "other_layer"),
        ("上一版日主是甲", "other_layer"),
        ("修订前日主是甲", "other_layer"),
        ("流年日主是甲", "other_layer"),
        ("流月日主是甲", "other_layer"),
        ("流日的日主是甲", "other_layer"),
        ("次限本命太阳在狮子座", "other_layer"),
        ("行运太阳在狮子座", "other_layer"),
        ("命宫借星主星有紫微", "other_layer"),
        ("命宫三方四正主星有紫微", "other_layer"),
        ("书里写日主是甲", "quoted_or_reported"),
        ("原文日主是甲", "quoted_or_reported"),
        ("他说日主是甲", "quoted_or_reported"),
        ("她说日主是甲", "quoted_or_reported"),
        ("转述日主是甲", "quoted_or_reported"),
        ("据说日主是甲", "quoted_or_reported"),
        ("你曾说日主是甲", "quoted_or_reported"),
        ("有人说日主是甲", "quoted_or_reported"),
        ("> 日主是甲", "quoted_or_reported"),
        ("`日主是甲`", "quoted_or_reported"),
        ('"日主是甲"', "quoted_or_reported"),
        ("“日主是甲”", "quoted_or_reported"),
        ("「日主是甲」", "quoted_or_reported"),
        ("『日主是甲』", "quoted_or_reported"),
        ("‘日主是甲’", "quoted_or_reported"),
    ],
)
def test_guarded_claims_are_deferred_instead_of_becoming_false_positive_conflicts(
    bazi: dict, text: str, reason: str
) -> None:
    result = check_chart_consistency(text, bazi)
    assert result["data"]["status"] == "needs_review"
    assert all(
        row["outcome"] == "needs_review" and row["reason_code"] == reason
        for row in result["data"]["checks"]
    )
    assert result["data"]["coverage"]["checked"] == 0


@pytest.mark.parametrize(
    "text",
    [
        "“这是一段转述。日主是甲。还有别的话。”",
        "「这是一段转述。日主是甲。未闭合",
        '"转述一段话。日主是甲。"',
        "```text\n日主是甲。\n```",
        "`多句话。日主是甲。`",
    ],
)
def test_quotes_remain_protected_across_sentence_boundaries(
    bazi: dict, text: str
) -> None:
    result = check_chart_consistency(text, bazi)
    assert result["data"]["status"] == "needs_review"
    assert not any(
        row["outcome"] == "contradiction" for row in result["data"]["checks"]
    )


@pytest.mark.parametrize(
    "text",
    [
        "你已成正印格",
        "正印格已经成立",
        "你是正印格",
        "格局是正印格",
        "用神是壬",
        "用神已定为壬",
        "确定用神为壬",
        "唯一用神是庚",
        "你就是伤官格",
        "你已经确定成格",
        "扶抑候选天干唯一是壬",
        "调候候选天干已定为甲",
    ],
)
def test_screen_or_candidate_cannot_authorize_final_pattern_or_useful_assertions(
    bazi: dict, text: str
) -> None:
    result = check_chart_consistency(text, bazi)
    assert result["data"]["status"] == "needs_review"
    assert all(
        row["reason_code"] == "unsupported_or_nonfinal_assertion"
        for row in result["data"]["checks"]
    )


@pytest.mark.parametrize(
    "text",
    [
        "今天工作挺忙。",
        "无盘判断。",
        "",
        "\n\t",
        "买菜准备做饭",
        "关系需要现实沟通",
        "日主丙丁相见",
        "太阳晒得很暖和",
        "甲木",
        "丁火",
        "本次不进行命理计算",
        "Sun in Leo",
    ],
)
def test_unrecognized_narrative_is_not_reported_as_fully_validated(
    bazi: dict, text: str
) -> None:
    result = check_chart_consistency(text, bazi)
    assert result["data"]["status"] in ("not_checked", "needs_review")
    assert result["data"]["coverage"]["checked"] == 0


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-10-21的大运是庚午", "matched"),
        ("2026-10-21大运不是辛未", "matched"),
        ("2022-03-11的大运是己巳", "matched"),
        ("2022-03-12的大运是庚午", "needs_review"),
        ("2022-03-13的大运是庚午", "matched"),
        ("2032-03-11的大运是庚午", "matched"),
        ("2032-03-12的大运是辛未", "needs_review"),
        ("2032-03-13的大运是辛未", "matched"),
        ("2002-03-11的大运是戊辰", "needs_review"),
        ("2026-02-30的大运是庚午", "needs_review"),
        ("第十步大运是丁丑", "matched"),
        ("第三步大运是庚午", "matched"),
        ("第11步大运是丁丑", "not_checked"),
        ("今年大运是庚午", "needs_review"),
        ("32岁大运是庚午", "needs_review"),
        ("现在的大运是庚午", "needs_review"),
        ("第3步大运是甲丑", "needs_review"),
        ("日主是甲火", "needs_review"),
    ],
)
def test_dates_decadal_boundaries_and_invalid_numeric_assertions_are_explicit(
    bazi: dict, text: str, expected: str
) -> None:
    assert (
        check_chart_consistency(text, bazi)["data"]["checks"][0]["outcome"] == expected
    )


def test_independent_sentences_keep_independent_guards_and_offsets(bazi: dict) -> None:
    text = "如果日主是甲，正官格候选筛选通过。  日主是丁；日干不是丁。"
    result = check_chart_consistency(text, bazi)
    rows = result["data"]["checks"]
    assert [row["outcome"] for row in rows] == [
        "needs_review",
        "needs_review",
        "matched",
        "contradiction",
    ]
    assert [text[row["span"]["start"] : row["span"]["end"]] for row in rows] == [
        "如果日主是甲",
        "正官格候选筛选通过",
        "日主是丁",
        "日干不是丁",
    ]
    assert result["data"]["status"] == "inconsistent"

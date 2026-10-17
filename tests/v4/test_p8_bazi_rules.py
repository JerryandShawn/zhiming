"""Pure rules: textbook arithmetic, alternate branches and honest limitations."""

from __future__ import annotations

import itertools
import math

import pytest

from mingjing_core.calculations.bazi.calendar_layers import command_at
from mingjing_core.calculations.bazi.elements import (
    BRANCHES,
    HIDDEN,
    STEMS,
    relations,
    table,
    ten_god,
    ten_gods,
    validate_pillars,
)
from mingjing_core.calculations.bazi.stars import auxiliary_stars
from mingjing_core.calculations.bazi.strength import scores
from mingjing_core.calculations.bazi.structure import climate, patterns, useful

NATAL = {"year": "壬辰", "month": "甲辰", "day": "甲子", "hour": "庚午"}


def test_ten_gods_known_jia_and_yi_rows() -> None:
    assert [ten_god("甲", stem) for stem in STEMS] == [
        "比肩",
        "劫财",
        "食神",
        "伤官",
        "偏财",
        "正财",
        "七杀",
        "正官",
        "偏印",
        "正印",
    ]
    assert [ten_god("乙", stem) for stem in STEMS] == [
        "劫财",
        "比肩",
        "伤官",
        "食神",
        "正财",
        "偏财",
        "正官",
        "七杀",
        "正印",
        "偏印",
    ]
    for master, other in itertools.product(STEMS, repeat=2):
        assert ten_god(master, other) in {
            "比肩",
            "劫财",
            "食神",
            "伤官",
            "偏财",
            "正财",
            "七杀",
            "正官",
            "偏印",
            "正印",
        }


@pytest.mark.parametrize("invalid", ["", "甲乙", "木", "a"])
def test_invalid_stem_cannot_match_substring(invalid: str) -> None:
    with pytest.raises(ValueError):
        ten_god("甲", invalid)


def test_full_pillars_and_hidden_roles_keep_old_order() -> None:
    validate_pillars(NATAL)
    result = ten_gods(NATAL)
    assert len(result["complete_table"]) == 10
    assert result["pillars"]["year"]["hidden"] == [
        {"stem": "戊", "role": "本气", "ten_god": "偏财"},
        {"stem": "乙", "role": "中气", "ten_god": "劫财"},
        {"stem": "癸", "role": "余气", "ten_god": "正印"},
    ]
    assert result["pillars"]["hour"]["hidden"][1]["role"] == "余气"
    with pytest.raises(ValueError):
        validate_pillars(dict(NATAL, day="甲丑"))


def test_month_command_primary_schedule_and_half_open_boundaries() -> None:
    assert command_at("寅", 4.999999, "甲")["commanding_stem"] == "戊"
    assert command_at("寅", 5, "甲")["commanding_stem"] == "丙"
    assert command_at("寅", 10, "甲")["commanding_stem"] == "甲"
    assert command_at("寅", 31, "甲")["commanding_stem"] == "甲"
    # The cited source uses 壬 in 辰's middle segment, different from v3 癸.
    value = command_at("辰", 8, "甲")
    assert value["commanding_stem"] == "壬"
    assert value["also_in_v3_hidden_stems"] is False


def test_every_command_segment_boundary() -> None:
    for branch, schedule in table("month_command")["schedules"].items():
        start = 0
        for stem, days in schedule:
            assert command_at(branch, start, "甲")["commanding_stem"] == stem
            assert command_at(branch, start + days - 0.00001, "甲")["commanding_stem"] == stem
            start += days
        assert start == 30


@pytest.mark.parametrize("invalid", [-1, math.nan, math.inf, True])
def test_command_rejects_invalid_elapsed_days(invalid: float) -> None:
    with pytest.raises(ValueError):
        command_at("寅", invalid, "甲")


def test_strength_scores_can_be_recomputed_and_do_not_merge() -> None:
    result = scores(NATAL)
    first, second = result["methods"]
    assert first["score"] == pytest.approx(19.333333)
    assert second["score"] == 27.5
    assert first["score"] == pytest.approx(
        sum(row["contribution"] for row in first["roots"])
        + 40 * first["month_support"]
        + sum(row["supports"] for row in first["exposed"]) * 20 / 3
    )
    assert second["score"] == sum(row["score"] for row in second["axes"].values())
    assert result["editorial_status"] == "original_editorial_unreviewed"
    assert "combined_score" not in result


def test_strength_disagreement_is_retained() -> None:
    cases = (dict(NATAL, month=a + b) for a, b in itertools.product(STEMS, BRANCHES))
    found = next(row for row in (scores(value) for value in cases) if not row["agreement"])
    assert found["methods"][0]["conclusion"] != found["methods"][1]["conclusion"]


def test_eight_regular_and_four_following_screens_have_counterconditions() -> None:
    result = patterns(NATAL, scores(NATAL))
    assert len(result["regular_eight"]) == 8
    assert len(result["following"]) == 4
    for row in result["regular_eight"] + result["following"]:
        assert len(row["conditions"]) >= 3
        assert row["screen_passed"] == (not row["unsatisfied"])
        assert row["satisfied"] or row["unsatisfied"]
    assert result["establishment"] == "candidate_only"
    assert any(row["unsatisfied"] for row in result["following"])


def test_pattern_screen_positive_and_negative_are_both_observable() -> None:
    natal = {"year": "癸酉", "month": "辛酉", "day": "甲子", "hour": "戊辰"}
    result = patterns(natal, scores(natal))
    official = next(row for row in result["regular_eight"] if row["ten_god"] == "正官")
    assert official["screen_passed"]
    changed = dict(natal, hour="丁卯")
    blocked = next(row for row in patterns(changed, scores(changed))["regular_eight"] if row["ten_god"] == "正官")
    assert not blocked["screen_passed"]
    assert any("牵制" in name for name in blocked["unsatisfied"])


def test_climate_120_rows_are_traceable_and_not_full_book_claims() -> None:
    reference = table("climate")
    assert set(reference["rows"]) == {a + b for a in STEMS for b in BRANCHES}
    for master, month in itertools.product(STEMS, BRANCHES):
        row = climate(master, month)
        assert row["candidate_stems"]
        assert set(row["candidate_stems"]) <= set(STEMS)
        assert row["source_locator"] and row["source_paragraph_sha256"]
        assert row["conditional_reading_required"]
        assert "source_excerpt" not in row
        assert row["editorial_status"] == "machine_editorial_unreviewed"
        assert row["full_original_collation"] is False
        assert row["full_chapter_conditions_implemented"] is False
    assert climate("乙", "丑")["extraction_status"] == "seasonal_or_combined_editorial_excerpt"
    assert climate("乙", "丑")["basis_scope"] == "borrowed_winter_general_rule_no_month_specific_text"


def test_three_useful_proposals_keep_empty_intersection_and_disagreements() -> None:
    strength = scores(NATAL)
    pattern = patterns(NATAL, strength)
    climatic = climate("甲", "辰")
    result = useful(NATAL, strength, pattern, climatic)
    assert len(result["balancing"]) == 2
    sets = [
        {stem for row in result["balancing"] for stem in row["candidate_stems"]},
        set(climatic["candidate_stems"]),
        {stem for row in result["pattern"] for stem in row["candidate_stems"]},
    ]
    assert set(result["consensus_stems"]) == set.intersection(*sets)
    assert all(
        set(result["disagreements"][name]) == values - set(result["consensus_stems"])
        for name, values in zip(("扶抑", "调候", "格局"), sets, strict=True)
    )


def test_auxiliary_markers_have_eight_types_anchors_and_no_fate_claims() -> None:
    result = auxiliary_stars(NATAL)
    assert len(result["distinct_markers"]) == 8
    assert len(result["markers"]) == 11
    empty = next(row for row in result["markers"] if row["name"] == "空亡")
    assert empty["target_branches"] == ["戌", "亥"]
    lu = next(row for row in result["markers"] if row["name"] == "禄神")
    assert lu["target_branches"] == ["寅"]
    assert {row["anchor"]["pillar"] for row in result["markers"] if row["name"] == "驿马"} == {"year", "day"}
    yin = auxiliary_stars(dict(NATAL, day="乙丑"))
    assert next(row for row in yin["markers"] if row["name"] == "羊刃")["applicability"] == "not_defined_for_yin_stem"


def test_empty_decades_and_wenchang_textbook_with_earth_exception() -> None:
    lu = table("auxiliary_stars")["stem_tables"]["禄神"]
    wen = table("auxiliary_stars")["stem_tables"]["文昌"]
    assert "".join(wen[master] for master in STEMS) == "巳午申酉申酉亥子寅卯"
    for master in STEMS:
        food = next(stem for stem in STEMS if ten_god(master, stem) == "食神")
        if master not in "丙丁":
            assert wen[master] == lu[food]
    assert wen["丙"] != lu["戊"] and wen["丁"] != lu["己"]
    for index in range(60):
        day = STEMS[index % 10] + BRANCHES[index % 12]
        empty = next(row for row in auxiliary_stars(dict(NATAL, day=day))["markers"] if row["name"] == "空亡")
        used = {BRANCHES[(index // 10 * 10 + offset) % 12] for offset in range(10)}
        assert set(empty["target_branches"]) == set(BRANCHES) - used


def test_daily_relations_are_geometry_only() -> None:
    assert relations("甲子", "己丑") == ["地支六合", "天干五合"]
    assert relations("甲子", "丙午") == ["地支六冲"]
    assert HIDDEN["辰"] == "戊乙癸"

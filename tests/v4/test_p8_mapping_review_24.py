"""Review 24 preserves primary-source boundaries and explicit project choices."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest
from p8_rules_sample_context import make_data

from mingjing_core.adapters.charts.climate_review import reviewed_climate
from mingjing_core.adapters.charts.interactions_bazi import bazi_interactions
from mingjing_core.adapters.charts.named_bazi import named_stars, options
from mingjing_core.adapters.charts.rules import evaluate_rules, load_registry
from mingjing_core.adapters.charts.rules.registry import SCHOOLS, interaction_policy
from mingjing_core.calculations.bazi.elements import table
from mingjing_core.calculations.bazi.structure import climate

PILLARS = {"year": "壬辰", "month": "甲辰", "day": "庚子", "hour": "戊午"}


@pytest.mark.parametrize("school", ["调候", "盲派", "项目口径·子平视角"])
def test_unsupported_school_cannot_masquerade_as_a_sourced_priority(school: str) -> None:
    with pytest.raises(ValueError, match="排序口径"):
        evaluate_rules(make_data(PILLARS), school=school)
    with pytest.raises(ValueError, match="排序口径"):
        bazi_interactions(PILLARS, {"yearly": "丙午"}, school=school)


def test_priority_keys_are_stable_but_display_names_disclose_project_convention() -> None:
    policy = interaction_policy()
    assert SCHOOLS == ("子平", "通用")
    assert set(policy["priority_by_school"]) == set(SCHOOLS)
    assert policy["priority_labels"] == {"子平": "项目口径·子平视角", "通用": "项目口径·通用"}
    assert "未作专家校准" in policy["priority_source_status"]
    graph = bazi_interactions(PILLARS, {"yearly": "丙午"})
    assert graph["ordering_label"] == "项目口径·子平视角"
    assert graph["priority_labels"] == policy["priority_labels"]
    assert graph["annotation_version"] == "p8-u12-interaction-labels-v2-review24"
    assert graph["annotation_basis"]["palace_source"] == policy["palace_source"]
    assert "出处待核" in graph["annotation_basis"]["ten_god_traditional_mappings"]["female_source_status"]
    assert all(set(row["priority"]) == set(SCHOOLS) for row in graph["relations"])


def test_each_regular_pattern_uses_the_same_ten_god_domain_lookup() -> None:
    registry = load_registry()
    patterns = [row for row in registry["rules"] if row["condition_ref"] == "pattern_condition"]
    assert len(patterns) == 24
    mapping = registry["interaction_mapping"]["ten_god_domains"]
    for row in patterns:
        assert row["domains"] == mapping[row["parameters"]["god"]]
        assert set(row["priority"]) == set(SCHOOLS)
    assert all(row["school"] in SCHOOLS and "健康" not in row["domains"] for row in registry["rules"])


def test_traditional_family_mapping_retains_modern_and_pending_boundaries() -> None:
    policy = interaction_policy()
    assert policy["palace_source"]["chapter"].startswith("第二十三章")
    assert "年月日時" in policy["palace_source"]["basis"]
    assert "非第二十三章原文" in policy["palace_modern_mappings"]["month"]["status"]
    assert len(policy["palace_pending_claims"]) == 2
    family = policy["ten_god_traditional_mappings"]
    assert family["male_context"] == {
        "正印": "母",
        "偏财": "父",
        "正财": "妻",
        "正官": "子女",
        "七杀": "子女",
        "比肩": "兄弟",
    }
    assert "出处待核" in family["female_source_status"]
    assert "婚育意愿" in family["modern_boundary"]
    assert "性别认同" in family["modern_boundary"]


def test_tianyi_alternative_changes_geng_only_and_exposes_its_actual_source() -> None:
    schools = table("schools")
    original = schools["tianyi"]["combined_common"]["table"]
    alternative = schools["tianyi"]["combined_geng_xin_ma_hu"]["table"]
    assert {key for key in original if original[key] != alternative[key]} == {"庚"}
    assert original["庚"] == "丑未" and alternative["庚"] == "寅午"
    assert schools["defaults"]["tianyi"] == "combined_common"
    selected = options({"tianyi": "combined_geng_xin_ma_hu"})
    marker = next(row for row in named_stars(PILLARS, selected)["markers"] if row["name"] == "天乙贵人")
    assert marker["target_branches"] == ["寅", "午"]
    assert marker["source"].endswith("神峰通考")
    assert "天乙贵人" in marker["source_locator"]
    assert marker["source_status"] == "public_domain_transcription_not_original_facsimile"


@pytest.mark.parametrize("master,target", list(zip("乙丁己辛癸", "寅巳巳申亥", strict=True)))
def test_third_blade_table_is_explicitly_optional_and_not_a_verified_attribution(master: str, target: str) -> None:
    pillars = dict(PILLARS, day=master + "丑")
    selected = options({"blade": "yin_reverse_pending"})
    marker = next(row for row in named_stars(pillars, selected)["markers"] if row["name"] == "羊刃")
    assert marker["target_branches"] == [target]
    assert marker["source_status"] == "primary_attribution_pending_not_verified"
    assert "未找到" in marker["source_locator"]
    default = next(row for row in named_stars(pillars, options())["markers"] if row["name"] == "羊刃")
    assert default["applicability"] == "not_defined_for_yin_stem"


def test_climate_review_preserves_old_candidates_and_records_unimplemented_conditions() -> None:
    original = climate("乙", "申")
    before = deepcopy(original)
    row = reviewed_climate(original)
    assert original == before
    assert "source_review_24" not in original
    assert not any("佐神未全收" in item for item in original["table_limits"])
    assert any("佐神未全收" in item for item in row["table_limits"])
    assert row["candidate_stems"] == original["candidate_stems"] == ["己", "丙"]
    review = row["source_review_24"]
    assert review["seasonal_candidates"] == ["丙", "癸"]
    assert "不用己" in review["monthly_emphasis"]
    assert "项目月段摘表顺序" in review["ordering_decision"]
    assert "异本及原刊校勘" in review["not_implemented"]


def test_every_climate_candidate_and_legacy_table_byte_is_protected() -> None:
    path = Path(__file__).resolve().parents[2] / "mingjing_core/knowledge/p8_bazi/climate.json"
    assert hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == (
        "8fe8e8ee0ff2af8fba1daaa9f5ba0157b2513318dd1c1452f54163e6c9af20f4"
    )
    for key, row in table("climate")["rows"].items():
        original = climate(key[0], key[1])
        revised = reviewed_climate(original)
        assert revised["candidate_stems"] == row["candidate_stems"]
        assert revised["source_locator"] == row["source_locator"]
        assert revised["method"] == original["method"]

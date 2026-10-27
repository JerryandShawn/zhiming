"""Review 23 policy changes preserve physical ambiguity and suppress experiments."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.adapters.charts.p8_policy import frozen_rectification_state
from mingjing_core.adapters.charts.time_basis_readout import attach_readout


def chart(basis: str, instant: str = "instant-1") -> dict[str, Any]:
    return {
        "id": instant + ":" + basis,
        "time_basis": {"basis": basis, "instant_id": instant},
        "data": {
            "pillars": {
                key: {"ganzhi": value, "gan": value[0], "zhi": value[1]}
                for key, value in zip(
                    ("year", "month", "day", "hour"),
                    ("甲子", "丙寅", "戊辰", "壬子"),
                    strict=True,
                )
            }
        },
        "ziwei_column": {"palaces": [], "ming_gong": "子", "shen_gong": "午"},
    }


def result(confirmation: bool = False) -> dict[str, Any]:
    return {"instants": [{"requires_confirmation": confirmation}], "limits": []}


def test_experiment_is_hidden_and_cannot_be_enabled_by_mutating_capability_copy() -> (
    None
):
    first = P8ChartAdapter.capabilities()
    assert first["rectification"]["status"] == "experimental_frozen"
    assert first["rectification"]["public_tools"] == []
    first["rectification"]["enabled_for_interpretation"] = True
    assert not P8ChartAdapter.capabilities()["rectification"][
        "enabled_for_interpretation"
    ]
    assert not P8ChartAdapter.capabilities()["rectification"]["visible_by_default"]
    assert not hasattr(P8ChartAdapter, "rectify")
    assert frozen_rectification_state()["conclusion"] == "分不出来"


def test_equal_results_have_one_visible_primary_without_hiding_diagnostics() -> None:
    rows = [chart(basis) for basis in ("standard", "true_solar", "beijing_standard")]
    raw = result()
    readout = attach_readout(raw, rows)
    assert raw["selected_basis"] == "true_solar"
    assert readout["primary_chart_ids"] == ["instant-1:true_solar"]
    assert readout["comparisons"] == []
    assert [row["id"] for row in rows if row["visible_by_default"]] == [
        "instant-1:true_solar"
    ]
    assert raw["requires_confirmation"] is False


@pytest.mark.parametrize("system", ["bazi", "ziwei"])
def test_any_pillar_or_palace_difference_shows_the_beijing_result(system: str) -> None:
    primary, other = chart("true_solar"), chart("beijing_standard")
    if system == "bazi":
        other["data"]["pillars"]["hour"] = {"ganzhi": "癸丑", "gan": "癸", "zhi": "丑"}
    else:
        other["ziwei_column"]["ming_gong"] = "丑"
    readout = attach_readout(result(), [primary, other])
    comparison = readout["comparisons"][0]
    assert comparison["fields_changed"] == [
        "bazi.pillars.hour" if system == "bazi" else "ziwei.ming_gong"
    ]
    assert comparison["text"].startswith("按北京时间则为")
    assert other["interpretation_role"] == "comparison" and other["visible_by_default"]


def test_school_preference_does_not_select_one_physical_fold_or_change_pillars() -> (
    None
):
    rows = [
        chart(basis, instant)
        for instant in ("fold0", "fold1")
        for basis in ("true_solar", "beijing_standard")
    ]
    before = deepcopy(rows)
    raw = result(True)
    readout = attach_readout(raw, rows)
    assert len(readout["primary_chart_ids"]) == 2
    assert (
        raw["requires_confirmation"]
        and readout["physical_instant_confirmation_required"]
    )
    assert [row["data"] for row in rows] == [row["data"] for row in before]


def test_gap_has_no_primary_chart_and_requires_record_confirmation() -> None:
    raw = result(True)
    readout = attach_readout(raw, [])
    assert raw["selected_basis"] is None
    assert readout["primary_chart_ids"] == []
    assert readout["physical_instant_confirmation_required"]

"""U2 negative cases, source pointers, symbol directions and clipped windows."""

from __future__ import annotations

import json
import math
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.interactions_bazi import bazi_interactions
from mingjing_core.adapters.charts.interactions_transits import (
    _error,
    _windows,
    transit_windows,
)
from mingjing_core.adapters.charts.interactions_ziwei import yearly_mutagen_links
from mingjing_core.calculations.bazi.elements import HIDDEN

NATAL = {"year": "壬辰", "month": "甲辰", "day": "甲子", "hour": "庚午"}
ROOT = Path(__file__).resolve().parents[2]


def test_layers_graph_preserves_ten_gods_directions_and_pillars() -> None:
    result = bazi_interactions(
        NATAL, {"decadal": "己丑", "yearly": "丙午", "daily": "辛卯"}
    )
    nodes = {node["id"]: node for node in result["nodes"]}
    assert nodes["target.decadal"]["stem_ten_god"] == "正财"
    combine = next(row for row in result["relations"] if row["kind"] == "天干五合")
    assert {node["ganzhi"][0] for node in combine["members"]} in [
        {"甲", "己"},
        {"丙", "辛"},
    ]
    controls = [row for row in result["relations"] if row["kind"] == "天干相克"]
    assert (
        any(
            row["source"] == "natal.hour" and row["target"] == "target.daily"
            for row in controls
        )
        is False
    )
    assert any(
        row["source"] == "natal.day" and row["target"] == "target.decadal"
        for row in controls
    )
    assert all(
        row["transformation_established"] is False for row in result["relations"]
    )
    assert all(
        any(node["id"].startswith("target.") for node in row["members"])
        for row in result["relations"]
    )
    assert len({row["id"] for row in result["relations"]}) == len(result["relations"])
    assert (
        bazi_interactions(
            dict(reversed(list(NATAL.items()))),
            {"daily": "辛卯", "yearly": "丙午", "decadal": "己丑"},
        )
        == result
    )


@pytest.mark.parametrize(
    ("kind", "natal_branch", "target"),
    [
        ("六冲", "子", "丙午"),
        ("六合", "子", "己丑"),
        ("六害", "子", "辛未"),
        ("六破", "子", "癸酉"),
    ],
)
def test_branch_pairs_have_actual_two_participants(
    kind: str, natal_branch: str, target: str
) -> None:
    result = bazi_interactions(NATAL, {"yearly": target})
    found = [row for row in result["relations"] if row["kind"] == kind]
    assert any(
        node["branch"] == natal_branch for row in found for node in row["members"]
    )
    assert all(len(row["members"]) == 2 for row in found)


def test_three_combinations_keep_missing_members_without_inventing_a_branch() -> None:
    incomplete = bazi_interactions(NATAL, {"yearly": "壬申"})
    complete = next(
        row
        for row in incomplete["relations"]
        if row["kind"] == "三合" and row["complete"]
    )
    assert complete["required_members"] == ["申", "子", "辰"]
    assert {node["id"] for node in complete["members"]} == {
        "target.yearly",
        "natal.day",
        "natal.year",
        "natal.month",
    }
    partial = bazi_interactions(NATAL, {"yearly": "庚寅"})
    fire = next(row for row in partial["relations"] if row["kind"] == "三合")
    assert fire["status"] == "incomplete_members" and fire["missing_branches"] == ["戌"]
    assert all(node["branch"] != "戌" for node in fire["members"])
    assert not any(row["kind"] == "三会" for row in incomplete["relations"])


def test_single_distinct_branch_never_becomes_incomplete_combination() -> None:
    natal = {"year": "甲子", "month": "丙子", "day": "戊子", "hour": "庚子"}
    result = bazi_interactions(natal, {"yearly": "壬子"})
    assert not any(
        row["kind"] in ("三合", "三会", "三刑", "自刑") for row in result["relations"]
    )


def test_three_punishments_keep_cycle_directions_and_self_punishment() -> None:
    natal = {"year": "甲寅", "month": "丙子", "day": "戊辰", "hour": "庚申"}
    result = bazi_interactions(natal, {"yearly": "己巳", "daily": "壬辰"})
    row = next(row for row in result["relations"] if row["kind"] == "三刑")
    assert row["complete"]
    assert {tuple(pair.values()) for pair in row["directed_pairs"]} == {
        ("natal.year", "target.yearly"),
        ("target.yearly", "natal.hour"),
        ("natal.hour", "natal.year"),
    }
    self_row = next(row for row in result["relations"] if row["kind"] == "自刑")
    assert {node["id"] for node in self_row["members"]} == {"natal.day", "target.daily"}


def test_selected_hidden_stems_are_explicit_and_do_not_mutate_legacy() -> None:
    hidden = dict(HIDDEN, 巳="丙庚戊")
    result = bazi_interactions(NATAL, {"yearly": "己巳"}, hidden_stems=hidden)
    assert [row["stem"] for row in result["nodes"][-1]["hidden_ten_gods"]] == list(
        "丙庚戊"
    )
    assert HIDDEN["巳"] == "丙戊庚"


@pytest.mark.parametrize(
    "layers", [{}, {"current": "丙午"}, {"yearly": "甲丑"}, {"daily": "ab"}]
)
def test_invalid_layer_does_not_produce_chart_evidence(layers: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        bazi_interactions(NATAL, layers)


def test_incomplete_hidden_table_rejected() -> None:
    with pytest.raises(ValueError):
        bazi_interactions(NATAL, {"yearly": "丙午"}, hidden_stems={"子": "癸"})


def _ziwei_data() -> dict:
    return {
        "palaces": [
            {"name": f"宫{i}", "index": i, "major": [{"name": f"星{i}"}], "minor": []}
            for i in range(12)
        ],
        "horoscope": {
            "target_date": "2026-10-18",
            "yearly": {
                "ganzhi": "丙午",
                "palace_names": [f"流宫{i}" for i in range(12)],
                "mutagen": [f"星{i}" for i in range(4)],
            },
        },
    }


def test_ziwei_resolves_real_star_positions_and_keeps_both_palace_scales() -> None:
    result = yearly_mutagen_links(_ziwei_data())
    assert result["complete"]
    assert result["links"][2]["locations"] == [
        {
            "natal_palace": "宫2",
            "palace_index": 2,
            "yearly_palace": "流宫2",
            "star_pointer": "/data/palaces/2",
        }
    ]


def test_missing_or_duplicate_stars_do_not_get_guessed_palaces() -> None:
    data = _ziwei_data()
    data["palaces"][0]["major"] = []
    data["palaces"][11]["minor"] = [{"name": "星1"}]
    result = yearly_mutagen_links(data)
    assert not result["complete"]
    assert (
        result["links"][0]["status"] == "missing"
        and result["links"][0]["locations"] == []
    )
    assert (
        result["links"][1]["status"] == "ambiguous"
        and len(result["links"][1]["locations"]) == 2
    )


def test_duplicate_palace_indices_rejected() -> None:
    data = _ziwei_data()
    data["palaces"][0]["index"] = 1
    with pytest.raises(ValueError):
        yearly_mutagen_links(data)


def test_windows_cross_360_and_distinguish_entry_exact_exit() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    points = [base + timedelta(hours=i) for i in range(13)]

    def error(point: datetime) -> float:
        return _error(357 + (point - base).total_seconds() / 7200, 0)

    rows = _windows(error, points, 2, [])
    assert len(rows) == 1
    assert rows[0]["entry_at"] == "2026-01-01T02:00:00Z"
    assert rows[0]["exact_at"] == ["2026-01-01T06:00:00Z"]
    assert rows[0]["exit_at"] == "2026-01-01T10:00:00Z"
    assert [row["phase"] for row in rows[0]["phases"]] == ["入相", "出相"]


def test_clipped_window_does_not_fabricate_entry_or_exact() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    points = [base, base + timedelta(hours=1)]
    rows = _windows(
        lambda point: 1 + (point - base).total_seconds() / 7200, points, 2, []
    )
    assert rows[0]["entry_at"] is None and rows[0]["exit_at"] is None
    assert rows[0]["exact_at"] == []
    assert rows[0]["start_clipped"] and rows[0]["end_clipped"]


def test_station_inside_one_orb_window_preserves_four_exact_passes() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    points = [base + timedelta(minutes=30 * i) for i in range(25)]

    def function(point: datetime) -> float:
        return math.sin((point - base).total_seconds() / 3600 - 1)

    stations = [
        base + timedelta(hours=1 + math.pi / 2),
        base + timedelta(hours=1 + 3 * math.pi / 2),
    ]
    rows = _windows(function, sorted(points + stations), 2, stations)
    assert len(rows) == 1 and len(rows[0]["exact_at"]) == 4
    assert len(rows[0]["phases"]) >= 6


@pytest.mark.parametrize("longitude", [math.nan, math.inf, -1, 361, True])
def test_invalid_longitude_rejected_before_loading_charts(longitude: float) -> None:
    with pytest.raises(ValueError):
        transit_windows(
            {"太阳": longitude}, "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"
        )


def test_native_chart_interactions_with_no_model_calls() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    process = subprocess.run(
        [python, "-X", "utf8", str(ROOT / "tests/test_p8_interactions_native.py")],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=180,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["tests"] == 5 and result["successful"] and result["skipped"] == 0

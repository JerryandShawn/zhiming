"""Evidence-preserving geometry and negative contracts for palace-stem flying."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.ziwei_flying import palace_flying_transformations
from mingjing_core.adapters.charts.ziwei_flying_support import BRANCHES, flying_profile


def sample() -> dict:
    profile = flying_profile()
    stars = list(dict.fromkeys(star for row in profile["table"].values() for star in row))
    palaces = [
        {
            "index": index,
            "name": f"本命宫{index}",
            "ganzhi": "甲乙丙丁戊己庚辛壬癸甲乙"[index] + branch,
            "major": [],
            "minor": [],
        }
        for index, branch in enumerate(BRANCHES)
    ]
    for index, star in enumerate(stars):
        tag = profile["labels"][profile["table"]["甲"].index(star)] if star in profile["table"]["甲"] else ""
        palaces[index % 12]["major"].append({"name": star, "mutagen": tag})
    return {
        "palaces": palaces,
        "horoscope": {
            "target_date": "2026-10-18",
            "yearly": {
                "index": 4,
                "ganzhi": "丙午",
                "palace_names": [f"流年宫{index}" for index in range(12)],
                "mutagen": profile["table"]["丙"],
            },
        },
    }


def pointer(data: dict, value: str):
    current = {"data": data}
    for part in value.split("/")[1:]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def test_flying_has_four_edges_per_source_and_exact_star_evidence() -> None:
    data = sample()
    before = copy.deepcopy(data)
    result = palace_flying_transformations(data)
    assert data == before
    assert len(result["edges"]) == 48 and result["complete"]
    assert result["school"] == "iztro-2.5.0-default-palace-stem-table"
    assert not result["rectification_scoring_used"]
    assert result["natal"]["complete"]
    for row in result["edges"]:
        source = row["source"]["palace_index"]
        target = row["locations"][0]["palace_index"]
        assert row["id"] in result["nodes"][source]["outgoing"]
        assert row["id"] in result["nodes"][target]["incoming"]
        assert pointer(data, row["locations"][0]["star_pointer"])["name"] == row["star"]
        assert all(pointer(data, path) is not None for path in row["evidence_paths"])


def test_self_transformation_requires_identical_palace_and_ji_opposite_is_geometry() -> None:
    result = palace_flying_transformations(sample())
    self_edge = result["edges"][0]
    assert self_edge["mutagen"] == "禄" and self_edge["self_transformation"]
    assert not result["edges"][1]["self_transformation"]
    for edge in result["edges"]:
        if edge["mutagen"] == "忌":
            assert edge["ji_opposition"]["palace_index"] == (edge["locations"][0]["palace_index"] + 6) % 12
            assert edge["ji_opposition"]["geometry_only"]
        else:
            assert edge["ji_opposition"] is None


def test_actual_yearly_stars_and_scale_are_not_replaced_by_our_named_table() -> None:
    data = sample()
    data["horoscope"]["yearly"]["mutagen"][2] = "左辅"
    result = palace_flying_transformations(data)
    yearly = result["temporal_layers"]["yearly"]
    assert yearly["status"] == "resolved" and not yearly["matches_named_table"]
    assert yearly["links"][2]["star"] == "左辅"
    assert yearly["life_palace"]["palace_index"] == 4
    for row in yearly["links"]:
        location = row["locations"][0]
        assert location["scope_palace"] == f"流年宫{location['palace_index']}"
    assert result["temporal_layers"]["decadal"]["status"] == "unavailable"
    assert result["temporal_layers"]["monthly"]["links"] == []


def test_missing_star_and_duplicate_star_remain_unresolved_without_self_claims() -> None:
    data = sample()
    data["palaces"][0]["major"] = []
    data["palaces"][11]["minor"].append({"name": "破军"})
    result = palace_flying_transformations(data)
    assert not result["complete"]
    missing, ambiguous = result["edges"][:2]
    assert missing["status"] == "missing" and missing["locations"] == []
    assert ambiguous["status"] == "ambiguous" and len(ambiguous["locations"]) == 2
    assert missing["self_transformation"] is ambiguous["self_transformation"] is None
    assert missing["ji_opposition"] is ambiguous["ji_opposition"] is None
    assert not result["natal"]["complete"]


def test_explicit_traditional_aliases_keep_original_star_pointer() -> None:
    data = sample()
    data["palaces"][0]["major"][0].update(name="廉貞", mutagen="祿")
    data["horoscope"]["yearly"]["mutagen"][0] = "天同"
    edge = palace_flying_transformations(data)["edges"][0]
    assert edge["status"] == "resolved" and edge["star"] == "廉贞"
    assert edge["locations"][0]["star_name"] == "廉貞"
    assert pointer(data, edge["locations"][0]["star_pointer"])["name"] == "廉貞"


def test_all_layer_indices_and_actual_mutagens_keep_separate_scales() -> None:
    data = sample()
    for index, layer in enumerate(("decadal", "yearly", "monthly", "daily")):
        data["horoscope"][layer] = {
            "index": index,
            "ganzhi": "甲寅",
            "palace_names": [f"{layer}{number}" for number in range(12)],
            "mutagen": flying_profile()["table"]["甲"],
        }
    result = palace_flying_transformations(data)
    assert len({row["life_palace"]["scope_palace"] for row in result["temporal_layers"].values()}) == 4
    for layer, value in result["temporal_layers"].items():
        assert value["matches_named_table"]
        assert all(path.startswith(f"/data/horoscope/{layer}/") for path in value["evidence_paths"])


@pytest.mark.parametrize("value", [True, 0.0, -1, 12, None])
def test_bad_palace_index_does_not_create_an_evidence_graph(value) -> None:
    data = sample()
    data["palaces"][0]["index"] = value
    with pytest.raises(ValueError, match="索引"):
        palace_flying_transformations(data)


@pytest.mark.parametrize("field,value", [("ganzhi", "甲子"), ("major", None), ("name", "")])
def test_bad_palace_fields_rejected(field: str, value) -> None:
    data = sample()
    data["palaces"][0][field] = value
    with pytest.raises(ValueError):
        palace_flying_transformations(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("index", True),
        ("ganzhi", "缺"),
        ("palace_names", ["重复"] * 12),
        ("mutagen", ["天同"] * 3),
        ("mutagen", ["天同"] * 4),
    ],
)
def test_malformed_present_layer_is_rejected_rather_than_invented(field: str, value) -> None:
    data = sample()
    data["horoscope"]["yearly"][field] = value
    with pytest.raises(ValueError):
        palace_flying_transformations(data)


def test_graph_output_is_byte_stable_and_reordered_palace_pointers_still_resolve() -> None:
    data = sample()
    first = json.dumps(palace_flying_transformations(data), ensure_ascii=False, sort_keys=True)
    assert json.dumps(palace_flying_transformations(data), ensure_ascii=False, sort_keys=True) == first
    data["palaces"].reverse()
    result = palace_flying_transformations(data)
    for edge in result["edges"]:
        assert pointer(data, edge["locations"][0]["star_pointer"])["name"] == edge["star"]


def test_native_iztro_flying_crosscheck() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    root = Path(__file__).resolve().parents[2]
    process = subprocess.run(
        [python, "-X", "utf8", str(root / "tests/test_p8_ziwei_native.py")],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        timeout=120,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result["successful"] and result["skipped"] == 0 and result["tests"] == 3

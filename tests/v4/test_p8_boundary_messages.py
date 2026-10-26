"""Templates report observed pillar differences and never invent an alternative."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.skills.boundary_messages import LABELS, render_boundary


def fixture() -> tuple[dict, dict, list]:
    path = (
        Path(__file__).resolve().parents[2]
        / "docs/v4/contracts/samples/ayuan_bazi.json"
    )
    preview = json.loads(path.read_text(encoding="utf8"))
    original = next(
        row
        for row in preview["aliases"]["r"]
        if row["ref"]["path"].startswith("/boundary_alerts/")
    )
    document = next(
        row["payload"]
        for row in preview["documents"]
        if row["document_id"] == original["ref"]["document_id"]
    )
    rule = {
        "alias": original["alias"],
        "path": original["ref"]["path"],
        "evidence_aliases": original["evidence_aliases"],
    }
    evidence = [
        {"alias": row["alias"], "path": row["ref"]["path"]}
        for row in preview["aliases"]["c"]
        if row["alias"] in rule["evidence_aliases"]
    ]
    return document, rule, evidence


def test_actual_ayuan_preserves_measured_seconds_and_only_hour_differs() -> None:
    document, rule, evidence = fixture()
    before = deepcopy(document)
    result = render_boundary(document, rule, evidence)
    assert result["affected_pillars"] == ["hour"]
    assert "380.537秒" in result["text"]
    assert (
        "年柱" not in result["text"]
        and "月柱" not in result["text"]
        and "日柱" not in result["text"]
    )
    assert f"〔{rule['alias']}〕" in result["text"]
    assert document == before
    brief = render_boundary(document, rule, evidence, brief=True)
    assert "前面说明" in brief["text"] and brief["state_writes"] == 0


@pytest.mark.parametrize("kind", LABELS)
def test_all_five_kinds_use_actual_pillars_and_allow_identical_sides(kind: str) -> None:
    document, rule, evidence = fixture()
    alert = document["boundary_alerts"][0]
    alert["boundary_kind"] = kind
    for alternative in alert["alternatives"]:
        alternative["pillars"] = deepcopy(alert["current_pillars"])
    result = render_boundary(document, rule, evidence)
    assert result["affected_pillars"] == []
    assert "未出现四柱差异" in result["text"]
    if kind == "eot_implementations":
        assert "实现差值是380.537秒" in result["text"]
        assert "几十秒" not in result["text"]


def test_eot_can_change_year_and_day_instead_of_hour() -> None:
    document, rule, evidence = fixture()
    alert = document["boundary_alerts"][0]
    alert["boundary_kind"] = "eot_implementations"
    for alternative in alert["alternatives"]:
        alternative["pillars"] = {
            **alert["current_pillars"],
            "year": "甲子",
            "day": "乙丑",
        }
    result = render_boundary(document, rule, evidence)
    assert result["affected_pillars"] == ["year", "day"]
    assert "时柱" not in result["text"]


@pytest.mark.parametrize(
    "mutation", ["false", "foreign", "missing", "nan", "unknown", "duplicate_alias"]
)
def test_unbound_or_invalid_alert_is_rejected(mutation: str) -> None:
    document, rule, evidence = fixture()
    alert = document["boundary_alerts"][0]
    if mutation == "false":
        alert["met"] = False
    elif mutation == "foreign":
        evidence[0]["path"] = "/interpretation"
    elif mutation == "missing":
        alert["alternatives"] = []
    elif mutation == "nan":
        alert["distance_seconds"] = float("nan")
    elif mutation == "duplicate_alias":
        evidence[1]["alias"] = evidence[0]["alias"]
    else:
        alert["boundary_kind"] = "other"
    with pytest.raises(ValueError):
        render_boundary(document, rule, evidence)

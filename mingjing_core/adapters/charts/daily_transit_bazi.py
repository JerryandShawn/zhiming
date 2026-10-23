"""Date-specific pillars and sourced natal-to-target structural conditions."""

from __future__ import annotations

from typing import Any

from ...calculations.bazi.calendar_layers import calendar_layers
from .daily_transit_natal import PreparedNatal
from .interactions_bazi import bazi_interactions
from .named_bazi import hidden_for, options, replace_layer_hidden

TEN_SOURCE = {
    "title": "项目既有五行阴阳十神算式；《三命通会》论五行生克公开转录",
    "locator": "mingjing_core/calculations/bazi/elements.py:ten_god",
    "status": "project_arithmetic_original_edition_collation_pending",
}


def bazi_day(prepared: PreparedNatal, day: str) -> dict[str, Any]:
    pillars = prepared.candidate["pillars"]
    selected = options(prepared.request.get("p8_options"))
    hidden = hidden_for(selected)
    daily = calendar_layers(prepared.bazi_engine, int(day[:4]), day, pillars)["day"]
    replace_layer_hidden(daily, hidden, pillars["day"][0])
    layers = {
        layer: daily[key]["ganzhi"]
        for key, layer in (("year", "yearly"), ("month", "monthly"), ("day", "daily"))
    }
    return {
        "natal_pillars": dict(pillars),
        "snapshot": daily,
        "selected_schools": selected,
        "interactions": bazi_interactions(pillars, layers, hidden_stems=hidden),
    }


def _relation_context(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "system": "bazi",
        "kind": "relation",
        "relation": row["kind"],
        "complete": row.get("complete", True),
        "natal_pillars": [
            item["id"].split(".")[1]
            for item in row["members"]
            if item["id"].startswith("natal.")
        ],
        "target_layers": [
            item["id"].split(".")[1]
            for item in row["members"]
            if item["id"].startswith("target.")
        ],
        "transformation_established": False,
    }


def bazi_hits(data: dict[str, Any]) -> list[dict[str, Any]]:
    graph = data["interactions"]
    source = {"title": "既有P8时间交互结构表", "references": graph["source_refs"]}
    hits = []
    for index, row in enumerate(graph["relations"]):
        context = _relation_context(row)
        if not context["natal_pillars"] or not context["target_layers"]:
            continue
        hits.append(
            {
                "rule_id": "daily.bazi.relation." + row["id"],
                "met": True,
                "school": graph["school"],
                "source": source,
                "context": context,
                "evidence_paths": [
                    f"/data/bazi/interactions/relations/{index}",
                    "/data/bazi/natal_pillars",
                ],
            }
        )
    for name, layer in (("year", "yearly"), ("month", "monthly"), ("day", "daily")):
        hits.append(
            {
                "rule_id": "daily.bazi.ten_god." + layer,
                "met": True,
                "school": "ziping-five-elements-polarity-project-v1",
                "source": TEN_SOURCE,
                "context": {
                    "system": "bazi",
                    "kind": "ten_god",
                    "layer": layer,
                    "ten_god": data["snapshot"][name]["stem_ten_god"],
                },
                "evidence_paths": [
                    f"/data/bazi/snapshot/{name}",
                    "/data/bazi/natal_pillars/day",
                ],
            }
        )
    return hits

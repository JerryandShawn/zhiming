"""Named palace-stem flying transformations, without event or fate scores."""

from __future__ import annotations

from typing import Any

from .ziwei_flying_support import (
    flying_profile,
    locate,
    palace_ref,
    palaces_by_index,
    star_positions,
    valid_ganzhi,
)

LAYERS = ("decadal", "yearly", "monthly", "daily")


def _edge(source: int, mutagen_index: int, palaces: dict, positions: dict, profile: dict) -> dict[str, Any]:
    origin = palace_ref(source, palaces)
    stem = origin["ganzhi"][0]
    star = profile["table"][stem][mutagen_index]
    result = {
        "id": f"palace-{source}-{mutagen_index}",
        "mutagen": profile["labels"][mutagen_index],
        "star": star,
        "source": origin,
        "table_ref": f"flying_v1.json#/table/{stem}/{mutagen_index}",
        **locate(star, positions),
    }
    result["evidence_paths"] = [origin["palace_pointer"] + "/ganzhi"] + [
        item["star_pointer"] for item in result["locations"]
    ]
    resolved = result["status"] == "resolved"
    target = result["locations"][0]["palace_index"] if resolved else None
    result["self_transformation"] = target == source if resolved else None
    result["ji_opposition"] = (
        {**palace_ref((target + 6) % 12, palaces), "relation": "对宫", "geometry_only": True}
        if resolved and result["mutagen"] == "忌"
        else None
    )
    return result


def _natal_tags(positions: dict, profile: dict) -> dict[str, Any]:
    rows = []
    for locations in positions.values():
        for location in locations:
            original = location["natal_mutagen"]
            label = {"祿": "禄", "權": "权"}.get(original, original)
            if label in (None, ""):
                continue
            if label not in profile["labels"]:
                raise ValueError("生年四化标签不在具名枚举中")
            rows.append(
                {
                    "mutagen": label,
                    "original_mutagen": original,
                    "star": location["canonical_star"],
                    "location": dict(location),
                    "evidence_paths": [location["star_pointer"] + "/mutagen"],
                }
            )
    counts = [sum(row["mutagen"] == label for row in rows) for label in profile["labels"]]
    return {
        "method": "actual_engine_natal_star_mutagen_tags",
        "links": rows,
        "complete": counts == [1, 1, 1, 1],
        "missing_or_ambiguous_labels": [
            label for label, count in zip(profile["labels"], counts, strict=True) if count != 1
        ],
    }


def _temporal_layer(name: str, value: Any, palaces: dict, positions: dict, profile: dict) -> dict[str, Any]:
    if value is None:
        return {"status": "unavailable", "reason": "actual_engine_layer_not_present", "links": []}
    if not isinstance(value, dict) or not valid_ganzhi(value.get("ganzhi")):
        raise ValueError("紫微运限干支缺失或无效")
    names, stars, index = value.get("palace_names"), value.get("mutagen"), value.get("index")
    if (
        not isinstance(names, list)
        or len(names) != 12
        or any(not isinstance(item, str) or not item for item in names)
        or len(set(names)) != 12
        or type(index) is not int
        or index not in range(12)
    ):
        raise ValueError("紫微运限命宫索引或十二宫名无效")
    if not isinstance(stars, list) or len(stars) != 4 or any(not isinstance(item, str) or not item for item in stars):
        raise ValueError("紫微运限四化缺失或无效")
    canonical = [profile["aliases"].get(star, star) for star in stars]
    if len(set(canonical)) != 4:
        raise ValueError("紫微运限四化星必须唯一")
    rows = []
    for ordinal, (label, star) in enumerate(zip(profile["labels"], canonical, strict=True)):
        row = {"mutagen": label, "star": star, "original_star": stars[ordinal], **locate(star, positions)}
        for location in row["locations"]:
            location["scope_palace"] = names[location["palace_index"]]
        row["evidence_paths"] = [f"/data/horoscope/{name}/mutagen/{ordinal}"] + [
            item["star_pointer"] for item in row["locations"]
        ]
        rows.append(row)
    return {
        "status": "resolved" if all(row["status"] == "resolved" for row in rows) else "incomplete",
        "ganzhi": value["ganzhi"],
        "life_palace": {**palace_ref(index, palaces), "scope_palace": names[index]},
        "palace_names": list(names),
        "matches_named_table": canonical == profile["table"][value["ganzhi"][0]],
        "links": rows,
        "evidence_paths": [f"/data/horoscope/{name}/{field}" for field in ("index", "ganzhi", "palace_names")],
    }


def palace_flying_transformations(data: dict[str, Any]) -> dict[str, Any]:
    """Keep missing/duplicate stars unresolved; do not manufacture absent layers."""
    profile = flying_profile()
    palaces = palaces_by_index(data)
    positions = star_positions(palaces, profile)
    edges = [_edge(source, ordinal, palaces, positions, profile) for source in range(12) for ordinal in range(4)]
    horoscope = data.get("horoscope", {})
    if not isinstance(horoscope, dict):
        raise ValueError("紫微运限结构无效")
    nodes = []
    for index in range(12):
        incoming = [
            edge["id"]
            for edge in edges
            if edge["status"] == "resolved" and edge["locations"][0]["palace_index"] == index
        ]
        nodes.append(
            {
                **palace_ref(index, palaces),
                "outgoing": [edge["id"] for edge in edges if edge["source"]["palace_index"] == index],
                "incoming": incoming,
            }
        )
    return {
        "version": profile["version"],
        "school": profile["school"],
        "claim_kind": profile["claim_kind"],
        "method": "declared_palace_stem_table_to_actual_natal_major_minor_stars",
        "table_sha256": profile["source_sha256"],
        "target_date": horoscope.get("target_date"),
        "nodes": nodes,
        "edges": edges,
        "complete": all(edge["status"] == "resolved" for edge in edges),
        "natal": _natal_tags(positions, profile),
        "temporal_layers": {
            name: _temporal_layer(name, horoscope.get(name), palaces, positions, profile) for name in LAYERS
        },
        "definitions": profile["definitions"],
        "source_refs": profile["source_refs"],
        "limits": profile["limits"],
        "rectification_scoring_used": False,
    }

"""Resolve U2 yearly transformations against real natal star positions."""

from __future__ import annotations

from typing import Any


def yearly_mutagen_links(data: dict[str, Any]) -> dict[str, Any]:
    """Never infer a star/palace when the actual engine field is absent."""
    palaces = data.get("palaces", [])
    yearly = data.get("horoscope", {}).get("yearly", {})
    if len(palaces) != 12 or {palace.get("index") for palace in palaces} != set(
        range(12)
    ):
        raise ValueError("紫微交互需要完整唯一的十二宫")
    names, mutagen = yearly.get("palace_names", []), yearly.get("mutagen", [])
    if len(names) != 12 or len(mutagen) != 4:
        raise ValueError("紫微交互缺少实际流年宫名或四化")
    rows = []
    for index, (label, star) in enumerate(
        zip(("禄", "权", "科", "忌"), mutagen, strict=True)
    ):
        matches = [
            palace
            for palace in palaces
            if any(
                item["name"] == star
                for item in palace.get("major", []) + palace.get("minor", [])
            )
        ]
        rows.append(
            {
                "id": f"yearly-mutagen-{index}",
                "mutagen": label,
                "star": star,
                "status": "resolved"
                if len(matches) == 1
                else "missing"
                if not matches
                else "ambiguous",
                "locations": [
                    {
                        "natal_palace": palace["name"],
                        "palace_index": palace["index"],
                        "yearly_palace": names[palace["index"]],
                        "star_pointer": f"/data/palaces/{palaces.index(palace)}",
                    }
                    for palace in matches
                ],
            }
        )
    return {
        "version": "p8-yearly-mutagen-links-v1",
        "method": "installed-py-iztro-horoscope-four-transformations-to-actual-stars",
        "school": "installed-py-iztro-default-not-independent-school-verification",
        "target_date": data["horoscope"].get("target_date"),
        "yearly_ganzhi": yearly.get("ganzhi"),
        "links": rows,
        "complete": all(row["status"] == "resolved" for row in rows),
        "source_refs": ["https://docs.iztro.com/posts/horoscope"],
        "limits": ["只关联已算出的流年四化，不新增宫干飞化、自化或现实事件预测。"],
    }

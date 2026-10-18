"""Validated positions and exact evidence pointers for named flying tables."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "寅卯辰巳午未申酉戌亥子丑"
TABLE_PATH = Path(__file__).resolve().parents[2] / "knowledge/p8_ziwei/flying_v1.json"


def flying_profile() -> dict[str, Any]:
    raw = TABLE_PATH.read_bytes()
    result = json.loads(raw)
    if set(result["table"]) != set(STEMS) or any(
        len(row) != 4 or len(set(row)) != 4 for row in result["table"].values()
    ):
        raise ValueError("宫干四化具名表不完整")
    result["source_sha256"] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    return result


def valid_ganzhi(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 2 and value[0] in STEMS and value[1] in BRANCHES


def palaces_by_index(data: dict[str, Any]) -> dict[int, tuple[int, dict[str, Any]]]:
    palaces = data.get("palaces")
    if not isinstance(palaces, list) or len(palaces) != 12:
        raise ValueError("宫干飞化需要完整十二宫")
    result = {}
    for position, palace in enumerate(palaces):
        if not isinstance(palace, dict):
            raise ValueError("紫微宫位字段无效")
        index = palace.get("index")
        if type(index) is not int or index not in range(12) or index in result:
            raise ValueError("紫微宫位索引必须唯一且为0至11整数")
        if not valid_ganzhi(palace.get("ganzhi")) or palace["ganzhi"][1] != BRANCHES[index]:
            raise ValueError("紫微宫干地支与实际宫位索引不符")
        if not isinstance(palace.get("name"), str) or not palace["name"]:
            raise ValueError("紫微宫名缺失")
        result[index] = position, palace
    if len({palace["name"] for _, palace in result.values()}) != 12:
        raise ValueError("紫微十二宫名必须唯一")
    return result


def star_positions(
    palaces: dict[int, tuple[int, dict[str, Any]]], profile: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for index, (position, palace) in sorted(palaces.items()):
        for group in ("major", "minor"):
            stars = palace.get(group)
            if not isinstance(stars, list):
                raise ValueError("宫干飞化需要实际主星与辅星数组")
            for star_index, star in enumerate(stars):
                if not isinstance(star, dict) or not isinstance(star.get("name"), str) or not star["name"]:
                    raise ValueError("紫微星曜名称无效")
                name = profile["aliases"].get(star["name"], star["name"])
                result.setdefault(name, []).append(
                    {
                        "palace_index": index,
                        "natal_palace": palace["name"],
                        "star_name": star["name"],
                        "canonical_star": name,
                        "star_pointer": f"/data/palaces/{position}/{group}/{star_index}",
                        "palace_pointer": f"/data/palaces/{position}",
                        "natal_mutagen": star.get("mutagen"),
                    }
                )
    return result


def palace_ref(index: int, palaces: dict[int, tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    position, palace = palaces[index]
    return {
        "palace_index": index,
        "natal_palace": palace["name"],
        "ganzhi": palace["ganzhi"],
        "palace_pointer": f"/data/palaces/{position}",
    }


def locate(star: str, positions: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    matches = positions.get(star, [])
    return {
        "status": "resolved" if len(matches) == 1 else "missing" if not matches else "ambiguous",
        "locations": [dict(item) for item in matches],
    }

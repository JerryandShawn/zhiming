"""Independent daily day-count/table/star-scan implementation for offline review.

The natal positions and declared table remain shared assumptions. This does not
claim another independent natal engine, school, or predictive validation.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from importlib.resources import files
from typing import Any

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ANCHOR = date(2000, 1, 7)
TABLE = {
    "甲": ("廉贞", "破军", "武曲", "太阳"),
    "乙": ("天机", "天梁", "紫微", "太阴"),
    "丙": ("天同", "天机", "文昌", "廉贞"),
    "丁": ("太阴", "天同", "天机", "巨门"),
    "戊": ("贪狼", "太阴", "右弼", "天机"),
    "己": ("武曲", "贪狼", "天梁", "文曲"),
    "庚": ("太阳", "武曲", "太阴", "天同"),
    "辛": ("巨门", "太阳", "文曲", "文昌"),
    "壬": ("天梁", "紫微", "左辅", "武曲"),
    "癸": ("破军", "巨门", "太阴", "贪狼"),
}
ENGLISH_STEMS = ("jia", "yi", "bing", "ding", "wu", "ji", "geng", "xin", "ren", "gui")
STAR_NAMES = {
    "lianzhenMaj": "廉贞",
    "pojunMaj": "破军",
    "wuquMaj": "武曲",
    "taiyangMaj": "太阳",
    "tianjiMaj": "天机",
    "tianliangMaj": "天梁",
    "ziweiMaj": "紫微",
    "taiyinMaj": "太阴",
    "tiantongMaj": "天同",
    "wenchangMin": "文昌",
    "jumenMaj": "巨门",
    "tanlangMaj": "贪狼",
    "youbiMin": "右弼",
    "wenquMin": "文曲",
    "zuofuMin": "左辅",
}


def day_ganzhi(value: date) -> str:
    """Count civil days from a declared 甲子 anchor; no calendar engine call."""
    if type(value) is not date:
        raise ValueError("reference_explicit_civil_date_required")
    distance = (value - ANCHOR).days
    return STEMS[distance % 10] + BRANCHES[distance % 12]


def extract_table(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf8")
        verified = {}
        for stem, english in zip(STEMS, ENGLISH_STEMS, strict=True):
            pattern = english + r"Heavenly:\{yinYang:[^{}]*?mutagen:\[([^\]]+)\]"
            matches = list(re.finditer(pattern, text))
            if len(matches) != 1:
                raise ValueError("reference_source_table_not_unique")
            match = matches[0]
            extracted = json.loads("[" + match[1] + "]")
            actual = tuple(STAR_NAMES[name] for name in extracted)
            if actual != TABLE[stem]:
                raise ValueError("reference_declared_table_differs_from_bundle")
            verified[stem] = {
                "stars": list(actual),
                "source_character_span": list(match.span()),
            }
    except (UnicodeError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("reference_source_table_parse_failed") from None
    return {
        "source": "installed_py_iztro/res/iztro-2.5.0.min.js",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "cells_verified": 40,
        "span_indexing": "unicode_codepoints_zero_based_half_open",
        "table": verified,
    }


def pinned_table() -> dict[str, Any]:
    raw = files("py_iztro.res").joinpath("iztro-2.5.0.min.js").read_bytes()
    return extract_table(raw)


def independent_links(ast: Any, value: date) -> list[dict[str, Any]]:
    """Scan original typed astrolabe stars, not the adapter flying graph."""
    result = []
    for label, name in zip(
        ("禄", "权", "科", "忌"), TABLE[day_ganzhi(value)[0]], strict=True
    ):
        matches = [
            {"palace_index": index, "natal_palace": palace.name}
            for index, palace in enumerate(ast.palaces)
            for star in palace.major_stars + palace.minor_stars
            if star.name == name
        ]
        result.append(
            {
                "mutagen": label,
                "star": name,
                "status": "resolved"
                if len(matches) == 1
                else "missing"
                if not matches
                else "ambiguous",
                "locations": matches,
            }
        )
    return result

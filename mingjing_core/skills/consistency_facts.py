"""Read only native primary facts; every value retains its original reference."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .learning_input import resolve_ref


def _fact(
    field: str, key: str, value: Any, ref: dict, path: str, school: Any, source: Any
) -> dict:
    return {
        "field": field,
        "key": key,
        "value": deepcopy(value),
        "ref": {"document_id": ref["document_id"], "path": ref["path"] + path},
        "school": deepcopy(school) if school else "school_unavailable",
        "source": deepcopy(source) if source else {"status": "source_unavailable"},
    }


def _bazi(data: dict, ref: dict, basis: dict) -> list[dict]:
    p8 = data.get("p8", {})
    rows = []
    stem = data.get("pillars", {}).get("day", {}).get("gan")
    if stem in tuple("甲乙丙丁戊己庚辛壬癸"):
        rows.append(
            _fact(
                "day_master",
                "",
                stem,
                ref,
                "/pillars/day/gan",
                basis.get("pillar_method", {}).get("day_hour"),
                {
                    "kind": "project_implementation",
                    "path": "mingjing_core/adapters/charts/time_basis_candidates.py",
                    "locator": "_candidate: declared coordinate getEightChar/setSect(1)/getDay",
                    "engine_versions": deepcopy(basis.get("engine_versions", {})),
                    "declared_method": deepcopy(basis.get("pillar_method", {})),
                    "method_ref": {
                        "document_id": ref["document_id"],
                        "path": ref["path"].removesuffix("/data")
                        + "/time_basis/pillar_method",
                    },
                    "concept_source": {
                        "path": "mingjing_core/calculations/bazi/elements.py",
                        "locator": "ten_gods: master=pillars[day][0]",
                    },
                },
            )
        )
    patterns = p8.get("patterns", {})
    for index, row in enumerate(patterns.get("regular_eight", [])):
        if type(row.get("screen_passed")) is bool:
            rows.append(
                _fact(
                    "pattern_screen",
                    row["pattern"],
                    row["screen_passed"],
                    ref,
                    f"/p8/patterns/regular_eight/{index}/screen_passed",
                    patterns.get("school"),
                    patterns.get("source"),
                )
            )
    rows.extend(_useful(p8.get("useful_candidates", {}), ref))
    decades = p8.get("decade_luck", {})
    for index, row in enumerate(decades.get("decades", [])):
        rows.append(
            _fact(
                "decade",
                str(row["index"]),
                row,
                ref,
                f"/p8/decade_luck/decades/{index}",
                decades.get("school"),
                decades.get("source"),
            )
        )
    return rows


def _useful(data: dict, ref: dict) -> list[dict]:
    school, source = data.get("school"), data.get("source")
    rows = []
    for index, row in enumerate(data.get("balancing", [])):
        rows.append(
            _fact(
                "useful",
                "扶抑:" + row["strength_method"],
                row["candidate_stems"],
                ref,
                f"/p8/useful_candidates/balancing/{index}/candidate_stems",
                school,
                source,
            )
        )
    climate = data.get("climate", {})
    if "candidate_stems" in climate:
        rows.append(
            _fact(
                "useful",
                "调候:",
                climate["candidate_stems"],
                ref,
                "/p8/useful_candidates/climate/candidate_stems",
                school,
                {
                    "source": source or {"status": "source_unavailable"},
                    "locator": climate.get("source_locator", "未提供定位"),
                },
            )
        )
    for index, row in enumerate(data.get("pattern", [])):
        rows.append(
            _fact(
                "useful",
                "格局:" + row["pattern"],
                row["candidate_stems"],
                ref,
                f"/p8/useful_candidates/pattern/{index}/candidate_stems",
                school,
                source,
            )
        )
    return rows


def _ziwei(data: dict, ref: dict) -> list[dict]:
    return [
        _fact(
            "ziwei_stars",
            row["name"] if row["name"] == "命宫" else row["name"] + "宫",
            [star["name"] for star in row["major"]],
            ref,
            f"/palaces/{index}/major",
            "installed-py-iztro-default",
            "https://docs.iztro.com/posts/palace",
        )
        for index, row in enumerate(data.get("palaces", []))
        if isinstance(row.get("major"), list)
    ]


def _astro(data: dict, ref: dict) -> list[dict]:
    return [
        _fact(
            "planet",
            name,
            row,
            ref,
            "/planets/" + name,
            data.get("method", "native-astro-method-unspecified"),
            "https://www.astro.com/swisseph/swephprg.htm",
        )
        for name, row in data.get("planets", {}).items()
        if isinstance(row, dict)
    ]


def primary_facts(chart: dict, documents: dict) -> list[dict]:
    readers = {"ziwei": _ziwei, "astro": _astro}
    rows = []
    for ref in chart["view"]["primary"]:
        data = resolve_ref(documents, ref)
        if chart["request"]["system"] == "bazi":
            parent = {
                "document_id": ref["document_id"],
                "path": ref["path"].removesuffix("/data"),
            }
            rows.extend(
                _bazi(data, ref, resolve_ref(documents, parent).get("time_basis", {}))
            )
        else:
            rows.extend(readers[chart["request"]["system"]](data, ref))
    return rows


def _covers_day(fact: dict, target: str) -> bool:
    """A date cannot pick a side when the nominal change happens during that day."""
    local_day = date.fromisoformat(target)
    start = datetime.combine(local_day, time(), timezone(timedelta(hours=8)))
    end = start + timedelta(days=1)
    row = fact["value"]
    left = datetime.fromisoformat(row["nominal_start_at"])
    right = datetime.fromisoformat(row["nominal_end_exclusive"])
    if left.tzinfo is None or right.tzinfo is None:
        raise ValueError("consistency_decade_timezone_missing")
    return left <= start and end <= right


def matching_facts(facts: list[dict], query: dict) -> list[dict]:
    rows = [row for row in facts if row["field"] == query["field"]]
    if query["field"] == "decade" and query.get("date"):
        try:
            return [row for row in rows if _covers_day(row, query["date"])]
        except (ValueError, KeyError, TypeError, OverflowError):
            return []
    key = query.get("key", "")
    if query["field"] == "useful" and key.endswith(":"):
        return [row for row in rows if row["key"].startswith(key)]
    return [row for row in rows if row["key"] == key]


def covering_alias(aliases: dict, ref: dict) -> str | None:
    rows = [
        row
        for name, row in aliases.items()
        if name.startswith("c")
        and row["ref"]["document_id"] == ref["document_id"]
        and (
            ref["path"] == row["ref"]["path"]
            or ref["path"].startswith(row["ref"]["path"] + "/")
        )
    ]
    return max(rows, key=lambda row: len(row["ref"]["path"]))["alias"] if rows else None

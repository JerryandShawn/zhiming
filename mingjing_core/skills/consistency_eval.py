"""Evaluate explicit assertions against verified facts, retaining uncertainty."""

from __future__ import annotations

from copy import deepcopy

from ..adapters.charts.tool_evidence import content_hash
from .consistency_facts import covering_alias, matching_facts


def _observed(fact: dict, query: dict):
    value = fact["value"]
    if query["field"] == "decade":
        if not isinstance(value.get("ganzhi"), str):
            raise ValueError("invalid_nominal_decade")
        return value["ganzhi"]
    if query["field"] == "planet":
        part = query["component"]
        if part == "position":
            if (
                value.get("sign")
                not in [
                    "白羊",
                    "金牛",
                    "双子",
                    "巨蟹",
                    "狮子",
                    "处女",
                    "天秤",
                    "天蝎",
                    "射手",
                    "摩羯",
                    "水瓶",
                    "双鱼",
                ]
                or type(value.get("longitude")) not in (int, float)
                or not 0 <= value["longitude"] < 360
            ):
                raise ValueError("invalid_natal_position")
            return {"sign": value["sign"], "degree": value["longitude"] % 30}
        if part == "house" and (
            type(value.get(part)) is not int or not 1 <= value[part] <= 12
        ):
            raise ValueError("invalid_natal_house")
        if part == "retrograde" and type(value.get(part)) is not bool:
            raise ValueError("invalid_natal_motion")
        return value[part]
    if query["field"] == "useful":
        if not isinstance(value, list) or any(
            stem not in tuple("甲乙丙丁戊己庚辛壬癸") for stem in value
        ):
            raise ValueError("invalid_candidate_stems")
        return sorted(value)
    return value


def _equal(observed, query: dict) -> bool:
    expected = query["value"]
    if query["field"] in ("useful", "ziwei_stars"):
        return not observed if expected == "空宫" else expected in observed
    if query["field"] == "planet" and query["component"] == "position":
        same_sign = observed["sign"] == expected["sign"]
        if expected["degree"] is None:
            return same_sign
        return (
            same_sign
            and abs(observed["degree"] - expected["degree"])
            <= expected["tolerance"] + 1e-9
        )
    return observed == expected


def _relevant_citation(name: str, facts: list[dict], aliases: dict) -> bool:
    row = aliases[name]
    if name.startswith("r"):
        return any(
            _relevant_citation(child, facts, aliases)
            for child in row["evidence_aliases"]
        )
    ref = row["ref"]
    return any(
        fact["ref"]["document_id"] == ref["document_id"]
        and (
            fact["ref"]["path"] == ref["path"]
            or fact["ref"]["path"].startswith(ref["path"] + "/")
        )
        for fact in facts
    )


def deferred(
    reason: str, *, outcome: str = "needs_review", field: str | None = None
) -> dict:
    return {
        "field": field,
        "outcome": outcome,
        "reason_code": reason,
        "assertion": None,
        "expected_values": [],
        "source_refs": [],
        "input_c_aliases": [],
        "input_r_aliases": [],
        "input_citations": "",
        "fact_sources": [],
    }


def evaluate(query: dict, facts: list[dict], aliases: dict, cited: list[str]) -> dict:
    if "reason" in query:
        return deferred(query["reason"])
    field = query["field"]
    if any(name not in aliases for name in cited):
        return deferred("citation_missing", field=field)
    selected = matching_facts(facts, query)
    if not selected:
        date_query = field == "decade" and query.get("date")
        return deferred(
            "date_outside_or_boundary" if date_query else "field_unavailable",
            outcome="needs_review" if date_query else "not_checked",
            field=field,
        )
    if any(not _relevant_citation(name, selected, aliases) for name in cited):
        return deferred("citation_not_supporting_field", field=field)
    proof = [covering_alias(aliases, row["ref"]) for row in selected]
    if any(name is None for name in proof):
        return deferred("field_evidence_missing", outcome="not_checked", field=field)
    try:
        observed = [_observed(row, query) for row in selected]
    except (KeyError, TypeError, AttributeError, ValueError):
        return deferred("field_incomplete", outcome="not_checked", field=field)
    if len({content_hash(value) for value in observed}) != 1:
        return deferred("multiple_methods_or_branches", field=field)
    equal = _equal(observed[0], query)
    matched = not equal if query.get("negative", False) else equal
    c_names = list(dict.fromkeys(proof))
    r_names = [name for name in dict.fromkeys(cited) if name.startswith("r")]
    return {
        "field": field,
        "outcome": "matched" if matched else "contradiction",
        "reason_code": "value_matches" if matched else "value_differs",
        "assertion": {
            key: deepcopy(query[key])
            for key in ("field", "key", "value", "negative", "component", "date")
            if key in query
        },
        "expected_values": deepcopy(observed),
        "source_refs": [deepcopy(row["ref"]) for row in selected],
        "input_c_aliases": c_names,
        "input_r_aliases": r_names,
        "input_citations": "".join("〔" + name + "〕" for name in c_names + r_names),
        "fact_sources": [
            {"school": deepcopy(row["school"]), "source": deepcopy(row["source"])}
            for row in selected
        ],
    }

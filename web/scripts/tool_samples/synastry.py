"""Read-only synastry comparison; a source fixture never grants new consent."""

from __future__ import annotations

import math
import re

from .bazi import synastry_bazi
from .common import (
    ASPECTS,
    INVALID_SOURCE,
    LIMITS,
    PILLARS,
    PLANETS,
    chinese,
    day,
    integer,
    need,
    number,
    pillars,
    pointer,
    verify,
)
from .source_catalog import evidence
from .summaries import synastry_summaries


def synastry_astro(value: dict) -> dict:
    orb = number(value["orb_degrees"], 0, 10)
    need(value["time_basis"] == "actual_UTC_not_true_solar")
    positions = {}
    for side in ("a", "b"):
        source = value[f"positions_{side}"]
        need(set(source) == set(PLANETS))
        positions[side] = {}
        for name in PLANETS:
            row = source[name]
            need(type(row["retrograde"]) is bool)
            positions[side][name] = {
                "longitude": number(row["longitude"], 0, math.nextafter(360, 0)),
                "retrograde": row["retrograde"],
            }
    aspects = []
    for row in value["aspects"]:
        need(row["from"] in PLANETS and row["to"] in PLANETS and row["aspect"] in ASPECTS)
        need(integer(row["angle"], 0, 180) == ASPECTS[row["aspect"]])
        error = number(row["orb_degrees"], 0, orb)
        delta = abs(positions["a"][row["from"]]["longitude"] - positions["b"][row["to"]]["longitude"])
        need(math.isclose(abs(min(delta, 360 - delta) - row["angle"]), error, rel_tol=0, abs_tol=1e-9))
        aspects.append({key: row[key] for key in ("from", "to", "aspect", "angle", "orb_degrees")})
    need(len({(row["from"], row["to"]) for row in aspects}) == len(aspects))
    return {
        "positions_a": positions["a"],
        "positions_b": positions["b"],
        "orb_degrees": orb,
        "aspects": aspects,
        "basis": "actual_UTC_not_true_solar",
    }


def palace(value: dict, name: str) -> dict:
    need(value["name"] == name)
    pair = pillars({key: value["ganzhi"] for key in PILLARS})["day"]
    stars = {key: [chinese(row["name"]) for row in value[key]] for key in ("major", "minor")}
    return {"name": name, "index": integer(value["index"], 0, 11), "ganzhi": pair, **stars}


def synastry_ziwei(value: dict) -> dict:
    need(value["compatibility_score"] is None)
    views = []
    for row in value["cross_views"]:
        need(row["recipient"] in ("a", "b") and type(row["same_branch"]) is bool)
        own, other = palace(row["own_spouse_palace"], "夫妻"), palace(row["other_life_palace"], "命宫")
        shared = [chinese(name) for name in row["shared_star_names"]]
        need(row["same_branch"] == (own["ganzhi"][-1] == other["ganzhi"][-1]))
        need(shared == sorted(set(own["major"] + own["minor"]).intersection(other["major"] + other["minor"])))
        views.append(
            {
                "recipient": row["recipient"],
                "own_spouse_palace": own,
                "other_life_palace": other,
                "same_branch": row["same_branch"],
                "shared_star_names": shared,
            }
        )
    need(len(views) == 2 and {row["recipient"] for row in views} == {"a", "b"})
    return {"cross_views": views, "compatibility_score": None}


def bazi_rule(rule: str, paths: list, data: dict) -> None:
    need(paths[1:] == ["/data/bazi/pillars_a", "/data/bazi/pillars_b"])
    path = paths[0]
    if rule == "synastry.bazi.day-stems-combine":
        need(path == "/data/bazi/day_stem_combination" and data["bazi"]["day_stem_combination"]["met"] is True)
    elif rule.startswith("synastry.bazi.branch-"):
        need(re.fullmatch(r"/data/bazi/branch_relations/(0|[1-9][0-9]*)", path) is not None)
        need(rule == "synastry.bazi.branch-" + pointer(data, path.removeprefix("/data"))["kind"])
    elif rule == "synastry.bazi.visible-element-complement":
        need(re.fullmatch(r"/data/bazi/element_complement/[01]", path) is not None)
        need(bool(pointer(data, path.removeprefix("/data"))["elements"]))
    else:
        need(rule == "synastry.bazi.useful-candidate-overlap")
        need(re.fullmatch(r"/data/bazi/useful_complement/[0-5]", path) is not None)
        need(bool(pointer(data, path.removeprefix("/data"))["overlap"]))


def verify_synastry_rules(root: dict, data: dict) -> None:
    for hit in root["rule_hits"]:
        rule, paths = hit["rule_id"], hit["evidence_paths"]
        need(isinstance(paths, list) and bool(paths))
        path = paths[0]
        if rule.startswith("synastry.bazi."):
            bazi_rule(rule, paths, data)
        elif rule.startswith("synastry.astro."):
            need(re.fullmatch(r"/data/astro/aspects/(0|[1-9][0-9]*)", path) is not None)
            aspect = pointer(data, path.removeprefix("/data"))
            need(rule == "synastry.astro." + aspect["aspect"])
            need(
                paths[1:]
                == [
                    "/data/astro/orb_degrees",
                    "/data/astro/positions_a/" + aspect["from"],
                    "/data/astro/positions_b/" + aspect["to"],
                ]
            )
        else:
            need(rule == "synastry.ziwei.spouse-life-readout" and len(paths) == 1)
            need(re.fullmatch(r"/data/ziwei/cross_views/[01]", path) is not None)
            need(hit["claim_kind"] == "computed_side_by_side_view_not_affinity_judgment")


def time_basis(source: dict) -> dict:
    basis = {}
    for side in ("a", "b"):
        view = source["time_basis"][side]
        need(view["primary"]["basis"] == "true_solar")
        need(view["primary"]["requires_confirmation"] is False)
        need(pillars(view["primary"]["pillars"]) == pillars(source["bazi"][f"pillars_{side}"]))
        comparisons = []
        for comparison in view["comparisons"]:
            need(comparison["basis"] in ("beijing_standard", "standard"))
            need(isinstance(comparison["fields_changed"], list))
            comparisons.append(
                {
                    "basis": comparison["basis"],
                    "has_reported_difference": bool(comparison["fields_changed"]),
                }
            )
        basis[side] = {"primary": "true_solar", "comparisons": comparisons}
    return basis


def project_synastry(root: dict) -> dict:
    try:
        verify(root, "p8-synastry-v1")
        source = root["data"]
        need(source["kind"] in ("romantic", "friendship", "collaboration"))
        need(source["consent"] == "user_confirmed")
        data = {
            "kind": source["kind"],
            "as_of_date": day(source["as_of_date"]),
            "sample_consent": "user_confirmed",
            "requires_fresh_consent": True,
            "bazi": synastry_bazi(source["bazi"]),
            "astro": synastry_astro(source["astro"]),
            "ziwei": synastry_ziwei(source["ziwei"]),
            "basis": time_basis(source),
        }
        verify_synastry_rules(root, data)
        return {
            "format": "frontend-tool-sample-v1",
            "tool": "synastry",
            "document_id": root["document_id"],
            "data": data,
            "evidence": evidence(root, synastry_summaries(root, data)),
            "effects": {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_only"},
            "limits": LIMITS + ["样例中的确认不代表用户已授权本次处理。", "不提供婚配百分比、人品或关系成败判断。"],
        }
    except INVALID_SOURCE:
        raise ValueError("tool_public_projection_invalid") from None

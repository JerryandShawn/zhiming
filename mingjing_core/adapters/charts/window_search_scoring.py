"""Transparent project ranking over content-bound daily signals, not predictions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .tool_evidence import content_hash, pointer


def category(context: dict) -> tuple[str | None, str | None]:
    system, kind = context.get("system"), context.get("kind")
    mapping = {
        ("bazi", "relation"): ("bazi_relation", "relation"),
        ("bazi", "ten_god"): ("bazi_ten_god", "ten_god"),
        ("ziwei", "mutagen"): ("ziwei_mutagen", "mutagen"),
        ("astro", "aspect"): ("astro_aspect", "aspect"),
    }
    family, field = mapping.get((system, kind), (None, None))
    return family, context.get(field) if field else None


def weight_of(context: dict, weights: dict, purpose: str) -> dict[str, Any]:
    family, label = category(context)
    choices = weights["purpose_weights"][purpose]
    if family not in choices or label not in choices[family]:
        return {"recognized": False, "reason": "unsupported_daily_condition"}
    base = choices[family][label]
    layers = context.get("target_layers", [context.get("layer")])
    factor = max(
        (weights["layer_factors"].get(layer, 1) for layer in layers), default=1
    )
    if context.get("system") == "astro":
        factor = 1
    incomplete = family == "bazi_relation" and context.get("complete") is False
    return {
        "recognized": True,
        "family": family,
        "label": label,
        "base_weight": base,
        "layer_factor": factor,
        "contribution": 0 if incomplete else base * factor,
        "reason": "incomplete_relation_zero_weight"
        if incomplete
        else "published_project_weight",
    }


def observation(daily: dict, hit: dict, day: str, index: int) -> dict:
    if hit.get("met") is not True or not hit.get("evidence_paths"):
        raise ValueError("window_daily_evidence_invalid")
    try:
        facts = [
            {"path": path, "value": deepcopy(pointer(daily, path))}
            for path in hit["evidence_paths"]
        ]
    except (TypeError, ValueError, KeyError, IndexError) as error:
        raise ValueError("window_daily_evidence_invalid") from error
    return {
        "date": day,
        "kind": "derived_copy_of_actual_daily_evidence",
        "daily_document_id": daily["document_id"],
        "daily_rule_index": index,
        "daily_hit": deepcopy(hit),
        "facts": facts,
        "facts_sha256": content_hash(facts),
        "provenance_paths_scope": "external_daily_document_not_local_pointers",
    }


def ranking_hit(
    observed: dict, weighted: dict, observation_index: int, purpose: str, weights: dict
) -> dict:
    return {
        "rule_id": f"window.{purpose}.{weighted['family']}.{weighted['label']}",
        "rules_version": weights["version"],
        "met": True,
        "school": weights["school"],
        "source": weights["source"],
        "date": observed["date"],
        "contribution": weighted["contribution"],
        "context": {**weighted, "purpose": purpose, "prediction_validated": False},
        "evidence_paths": [f"/data/observations/{observation_index}", "/data/weights"],
    }


def score_day(
    daily: dict, purpose: str, weights: dict, data: dict, hits: list[dict]
) -> dict:
    day = daily["data"]["date"]
    row = {
        "date": day,
        "score": 0,
        "positive_hits": [],
        "negative_hits": [],
        "neutral_hits": [],
    }
    for index, hit in enumerate(daily["rule_hits"]):
        weighted = weight_of(hit.get("context", {}), weights, purpose)
        if not weighted["recognized"]:
            data["ignored_conditions"].append(
                {"date": day, "daily_rule_index": index, **weighted}
            )
            continue
        observed = observation(daily, hit, day, index)
        data["observations"].append(observed)
        hits.append(
            ranking_hit(
                observed, weighted, len(data["observations"]) - 1, purpose, weights
            )
        )
        value = weighted["contribution"]
        group = (
            "positive_hits"
            if value > 0
            else "negative_hits"
            if value < 0
            else "neutral_hits"
        )
        row[group].append(
            {
                "rule_hit_index": len(hits) - 1,
                "contribution": value,
                "label": weighted["label"],
            }
        )
        row["score"] += value
    return row

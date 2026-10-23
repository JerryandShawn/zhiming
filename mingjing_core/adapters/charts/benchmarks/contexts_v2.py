"""Explicit C0-C4 ablations; condition hits cannot leak into lower configurations."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any


def systems(bundle: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted({row["system"] for row in bundle["artifacts"].values()}))


def fact_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(bundle)
    for artifact in result["artifacts"].values():
        p8 = artifact["data"].get("p8", {})
        for name in list(p8):
            if name.startswith("rule_") or name in ("rules", "assessments"):
                p8.pop(name)
    result.pop("features", None)
    # Profiles may carry input provenance; only calculated data enter this view.
    result.pop("profiles", None)
    return result


def hit_list(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    from ..rules import evaluate_rules

    hits = []
    for artifact in bundle["artifacts"].values():
        if artifact["system"] == "bazi":
            result = evaluate_rules(artifact["data"])
            hits.extend(
                {"system": "bazi", "artifact_id": artifact["id"], **row}
                for row in result["rule_hits"]
            )
    return hits


def context(
    configuration: str,
    bundle: dict[str, Any],
    skill_provider: Callable[[str], dict[str, Any]],
    rule_provider: Callable[[dict[str, Any]], list[dict[str, Any]]] = hit_list,
) -> dict[str, Any]:
    facts = fact_bundle(bundle) if configuration != "C0" else {}
    skill_rows = (
        tuple(skill_provider(system) for system in systems(bundle))
        if configuration in ("C2", "C3", "C4a", "C4b")
        else ()
    )
    hits = tuple(rule_provider(bundle)) if configuration in ("C3", "C4a", "C4b") else ()
    for hit in hits:
        artifact = bundle["artifacts"].get(hit.get("artifact_id"))
        if (
            hit.get("met") is not True
            or artifact is None
            or hit.get("system") != artifact["system"]
        ):
            raise ValueError("rule_hit_not_true_or_not_bound_to_current_artifact")
    return {
        "chart_bundle": facts if configuration not in ("C0", "C1") else {},
        "chart_text": json.dumps(
            [row["data"] for row in facts["artifacts"].values()], ensure_ascii=False
        )
        if configuration == "C1"
        else None,
        "skills": skill_rows,
        "rule_hits": hits,
    }


def specialist_context(value: dict[str, Any], system: str) -> dict[str, Any]:
    bundle = {
        "artifacts": {
            ident: row
            for ident, row in value["chart_bundle"]["artifacts"].items()
            if row["system"] == system
        }
    }
    return {
        "chart_bundle": bundle,
        "chart_text": None,
        "skills": tuple(row for row in value["skills"] if row["system"] == system),
        "rule_hits": tuple(
            row for row in value["rule_hits"] if row["system"] == system
        ),
    }

"""Calculation-only invariants across current candidates; no interpretation."""

from __future__ import annotations

from typing import Any

from .contracts import canonical


def conclusion_metadata(
    columns: dict[str, Any], candidate_ids: tuple[str, ...]
) -> dict[str, Any]:
    stable, conditional = [], []
    for pillar in ("year", "month", "day", "hour"):
        groups: dict[str, list[str]] = {}
        values = {}
        for ident in candidate_ids:
            value = (columns[ident].get("pillars") or {}).get(pillar)
            key = canonical(value)
            values[key] = value
            groups.setdefault(key, []).append(ident)
        complete = "null" not in groups
        for key, identities in groups.items():
            if values[key] is None:
                continue
            item = {
                "field": f"pillars.{pillar}",
                "value": values[key],
                "candidate_ids": identities,
                "kind": "calculation_only_no_fortune_interpretation",
                "scope": "current_candidates_only",
                "complete_across_candidates": complete,
            }
            (stable if complete and len(groups) == 1 else conditional).append(item)
    return {
        "stable_conclusions": stable,
        "conditional_conclusions": conditional,
        "interpretation_status": "no_interpretive_conclusions_generated",
    }


def holdout_ranks(scores: list[int], used: bool) -> list[dict[str, Any]]:
    return [
        {
            "holdout_rank": sum(value >= score for value in scores) if used else None,
            "holdout_rank_bounds": (
                [
                    1 + sum(value > score for value in scores),
                    sum(value >= score for value in scores),
                ]
                if used
                else None
            ),
        }
        for score in scores
    ]

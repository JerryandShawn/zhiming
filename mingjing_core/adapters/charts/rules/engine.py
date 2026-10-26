"""Pure evaluation over supplied P8 facts; no aliases, storage or model calls."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ....domain.json_values import ensure_finite_json
from .conditions import CONDITIONS
from .registry import SCHOOLS, load_registry


def evaluate_rules(
    data: dict[str, Any], *, graph: dict[str, Any] | None = None, school: str = "子平"
) -> dict[str, Any]:
    if school not in SCHOOLS:
        raise ValueError("需要具名规则排序口径")
    ensure_finite_json(data)
    selected = data["p8"].get("time_interactions", {}) if graph is None else graph
    ensure_finite_json(selected)
    registry = load_registry()
    assessments = []
    for row in registry["rules"]:
        assessment = CONDITIONS[row["condition_ref"]](data, row["parameters"], selected)
        if (
            set(assessment) != {"met", "evidence_paths", "details"}
            or type(assessment["met"]) is not bool
        ):
            raise ValueError("纯条件结果违反契约")
        assessments.append(dict(deepcopy(row), **assessment))
    assessments.sort(key=lambda row: (row["priority"][school], row["rule_id"]))
    return {
        "version": registry["version"],
        "selected_school": school,
        "priority_status": "project_convention_not_expert_calibrated",
        "rule_hits": [deepcopy(row) for row in assessments if row["met"]],
        "assessments": assessments,
        "graph_binding": (
            "evidence paths refer to supplied graph bound at /data/p8/time_interactions"
        ),
        "limits": registry["limits"],
    }

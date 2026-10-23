"""Read evaluator chart fields from the current run's persisted native artifacts."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.charts_service import verify_calculation_scope
from mingjing_core.domain.contracts import CoreError


def chart_observations(rows: list[dict[str, Any]], owner: str, run: dict[str, Any]) -> dict[str, Any]:
    if run.get("status") != "succeeded":
        return {}
    values = []
    for row in rows:
        artifact = row.get("artifact") or {}
        profile = row.get("profile") or {}
        if (
            row.get("status") != "active"
            or row.get("owner_user_id", row.get("owner")) != owner
            or row.get("subject_id") != run.get("subject")
            or row.get("run_id") != run.get("id")
            or row.get("epoch") != run.get("retry_epoch")
            or artifact.get("system") != "bazi"
            or artifact.get("time_scale") not in {"natal", "natal_with_explicit_separate_target_layers"}
        ):
            continue
        # Revalidate scope and real JSON pointer/value links before projecting.
        calculation = {
            "profiles": {profile.get("id"): profile},
            "artifacts": {artifact.get("id"): artifact},
            "features": row.get("features", {}),
            "branches": [
                {
                    "id": artifact.get("branch_id"),
                    "owner_user_id": owner,
                    "subject_id": run.get("subject"),
                    "revision": artifact.get("revision"),
                }
            ],
            "errors": [],
        }
        try:
            verify_calculation_scope(calculation, owner, run["subject"], artifact["revision"], system="bazi")
        except (CoreError, KeyError, TypeError, ValueError):
            continue
        data = artifact.get("data", {})
        day = data.get("pillars", {}).get("day", {})
        if data.get("day_master") and day.get("gan") == data["day_master"]:
            values.append({"day_master": data["day_master"], "day_pillar": day.get("ganzhi")})
    # Multiple birth branches with different masters must not become one answer.
    if not values or any(value != values[0] for value in values):
        return {}
    return dict(values[0], source_store="core_entities.artifact.data", run_id=run["id"], epoch=run["retry_epoch"])

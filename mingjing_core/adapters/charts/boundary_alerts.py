"""M3 additive boundary warnings; keep default formulas and birth facts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .adapter import stable_id
from .boundary_candidates import SCHOOL, clock_sides, jie_sides, sample_at
from .boundary_solar_reference import reference_solar_coordinate
from .worker import load_engine

VERSION = "p8-boundary-alerts-v1"
POLICY_SOURCE = "docs/v4/evidence/P8/night28-boundary-policy.md"


def _near_clock(
    coordinate: datetime, hours: tuple[int, ...], threshold: int
) -> list[tuple[datetime, float]]:
    day = coordinate.replace(hour=0, minute=0, second=0, microsecond=0)
    points = [
        day + timedelta(days=delta, hours=hour)
        for delta in (-1, 0, 1)
        for hour in hours
    ]
    return [
        (point, abs((coordinate - point).total_seconds()))
        for point in points
        if abs((coordinate - point).total_seconds()) <= threshold
    ]


def _alert(
    candidate: dict[str, Any],
    prefix: str,
    kind: str,
    boundary: str,
    distance: float,
    threshold: int | None,
    alternatives: list[dict[str, Any]],
) -> dict[str, Any]:
    row = {
        "rule_id": "time_boundary." + kind,
        "rules_version": VERSION,
        "matched": True,
        "met": True,
        "critical": True,
        "boundary_kind": kind,
        "boundary_at": boundary,
        "boundary_basis": "physical_UTC+8"
        if kind == "jie_month"
        else "true_solar_coordinate",
        "distance_seconds": distance,
        "threshold_seconds": threshold,
        "source_instant_id": candidate["instant_id"],
        "instant_id": candidate["instant_id"],
        "source_utc": candidate["utc"],
        "current_pillars": dict(candidate["pillars"]),
        "alternatives": alternatives,
        "school": SCHOOL,
        "source": POLICY_SOURCE,
        "evidence_paths": [
            prefix + "/coordinate_datetime",
            prefix + "/pillars",
            prefix + "/solar_time",
        ],
        "text": (
            "临界：请把下列候选并列核对；敏感性采样不是新的出生事实，"
            "不据此改档或倒推时辰。"
        ),
        "default_formula_changed": False,
    }
    row["id"] = stable_id("boundary-", row)
    return row


def _clock_alerts(
    candidate: dict[str, Any], prefix: str, engine: Any
) -> list[dict[str, Any]]:
    coordinate = datetime.fromisoformat(candidate["coordinate_datetime"])
    longitude = candidate["solar_time"]["longitude"]
    rows = []
    specifications = (
        ("hour_branch", tuple(range(1, 24, 2))),
        ("late_zi_day", (23,)),
        ("zi_midnight", (0,)),
    )
    for kind, hours in specifications:
        for boundary, distance in _near_clock(coordinate, hours, 900):
            alternatives = clock_sides(
                engine, boundary, longitude, midnight=kind == "zi_midnight"
            )
            rows.append(
                _alert(
                    candidate,
                    prefix,
                    kind,
                    boundary.isoformat(),
                    distance,
                    900,
                    alternatives,
                )
            )
    return rows


def _jie_alerts(
    candidate: dict[str, Any], prefix: str, engine: Any
) -> list[dict[str, Any]]:
    jie = candidate["jie_uncertainty"]
    if jie["distance_seconds"] > 7200:
        return []
    boundary = datetime.fromisoformat(jie["calendar_boundary"])
    alternatives = jie_sides(engine, boundary, candidate["solar_time"]["longitude"])
    row = _alert(
        candidate,
        prefix,
        "jie_month",
        boundary.isoformat(),
        jie["distance_seconds"],
        7200,
        alternatives,
    )
    row["jie"] = jie["nearest_jie"]
    row["evidence_paths"].append(prefix + "/jie_uncertainty")
    row["id"] = stable_id(
        "boundary-", {key: value for key, value in row.items() if key != "id"}
    )
    return [row]


def _eot_alerts(
    candidate: dict[str, Any], prefix: str, engine: Any
) -> list[dict[str, Any]]:
    utc = datetime.fromisoformat(candidate["utc"].replace("Z", "+00:00")).astimezone(
        UTC
    )
    reference = reference_solar_coordinate(utc, candidate["solar_time"]["longitude"])
    coordinate = datetime.fromisoformat(reference["coordinate_datetime"])
    alternative = sample_at(
        engine, utc, coordinate, "independent_EOT_same_physical_instant"
    )
    alternative["coordinate_method"] = reference["method"]
    if alternative["pillars"] == candidate["pillars"]:
        return []
    default = datetime.fromisoformat(candidate["coordinate_datetime"])
    distance = abs((coordinate - default).total_seconds())
    row = _alert(
        candidate,
        prefix,
        "eot_implementations",
        default.isoformat(),
        distance,
        None,
        [alternative],
    )
    row["reference"] = reference
    row["id"] = stable_id(
        "boundary-", {key: value for key, value in row.items() if key != "id"}
    )
    return [row]


def boundary_alerts(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept time_basis_candidates; pointers use response /time_basis root."""
    rows = []
    engine = None
    for group_index, group in enumerate(result["items"]):
        for index, candidate in enumerate(group["source_variants"]):
            if candidate["basis"] != "true_solar":
                continue
            if engine is None:
                engine = load_engine("bazi")
            prefix = f"/time_basis/items/{group_index}/source_variants/{index}"
            rows += _clock_alerts(candidate, prefix, engine)
            rows += _jie_alerts(candidate, prefix, engine)
            rows += _eot_alerts(candidate, prefix, engine)
    return rows

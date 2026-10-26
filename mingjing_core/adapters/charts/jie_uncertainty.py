"""Minute-engine sampling around the explicit two-minute Jie uncertainty band."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ...calculations.bazi.calendar_layers import solar_at
from .adapter import parse_datetime, stable_id, validated_number


def boundaries_in_range(engine: Any, start: str, end: str, tz: float) -> list[dict[str, Any]]:
    """Enumerate real Jie inside the declared range, independently of its centers."""
    left, right = parse_datetime(start), parse_datetime(end)
    if right < left or right - left > timedelta(days=2):
        raise ValueError("节界枚举范围须非负且不超过48小时")
    offset = validated_number(tz, "出生时UTC偏移", -14, 14)
    calendar_left = left + timedelta(hours=8 - offset)
    calendar_right = right + timedelta(hours=8 - offset)
    cursor, rows = calendar_left - timedelta(seconds=1), []
    for _ in range(8):
        item = solar_at(engine, cursor).getLunar().getNextJie()
        if item is None:
            raise ValueError("排盘引擎没有返回可枚举的下一节")
        boundary = datetime.fromisoformat(item.getSolar().toYmdHms())
        if boundary <= cursor:
            raise ValueError("排盘引擎节界没有向前推进")
        if boundary > calendar_right:
            return rows
        if boundary >= calendar_left:
            rows.append(_range_boundary(item.getName(), boundary, left, right, offset))
        cursor = boundary
    raise ValueError("节界枚举超出有限预算")


def _range_boundary(name: str, calendar: datetime, left: datetime, right: datetime, offset: float) -> dict[str, Any]:
    civil = calendar + timedelta(hours=offset - 8)
    floor = civil.replace(second=0, microsecond=0)
    before = floor if civil.second or civil.microsecond else floor - timedelta(minutes=1)
    after = floor + timedelta(minutes=1)
    sides = {"before": before, "after": after}
    return {
        "jie": name,
        "calendar_boundary": calendar.isoformat() + "+08:00",
        "civil_boundary": civil.isoformat(),
        "samples": [point.strftime("%Y-%m-%d %H:%M") for point in sides.values() if left <= point <= right],
        "strict_sides_within_declared_range": {key: left <= point <= right for key, point in sides.items()},
        "enumeration": "real_getNextJie_only_inside_declared_range_not_near_center_probe",
        "declared_range": {"start": left.isoformat(), "end": right.isoformat(), "inclusive": True},
    }


def probe(engine: Any, civil: str, tz: float) -> dict[str, Any] | None:
    point = datetime.strptime(civil, "%Y-%m-%d %H:%M")
    calendar = point + timedelta(hours=8 - tz)
    lunar = solar_at(engine, calendar).getLunar()
    candidates = []
    for item in (lunar.getPrevJie(), lunar.getNextJie()):
        boundary = datetime.fromisoformat(item.getSolar().toYmdHms())
        candidates.append((abs((calendar - boundary).total_seconds()), item.getName(), boundary))
    distance, name, boundary = min(candidates)
    if distance > 120:
        return None
    civil_boundary = boundary + timedelta(hours=tz - 8)
    floor = civil_boundary.replace(second=0, microsecond=0)
    before = floor if civil_boundary.second else floor - timedelta(minutes=1)
    after = floor + timedelta(minutes=1)
    return {
        "jie": name,
        "calendar_boundary": boundary.isoformat() + "+08:00",
        "civil_boundary": civil_boundary.isoformat(),
        "distance_seconds": distance,
        "samples": [before.strftime("%Y-%m-%d %H:%M"), after.strftime("%Y-%m-%d %H:%M")],
        "range": {
            "start": (floor - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M"),
            "end": (after + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M"),
            "inclusive": True,
        },
    }


def expand(branch: dict[str, Any], value: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for point in sorted({branch["civil_datetime"], *value["samples"]}):
        row = dict(branch)
        row.update(
            id=stable_id("time-", [branch["id"], "jie-uncertain-v1", point, value]),
            civil_datetime=point,
            input_precision="interval",
            coverage="sampled_not_continuous",
            confirmed_birth_time=False,
            sampling_range={
                **value["range"],
                "declared_sampling_range": branch["sampling_range"],
                "kind": "calendar_boundary_sensitivity_not_new_birth_fact",
            },
            warnings=[
                *branch["warnings"],
                "节界不确定：±2分钟内做口径敏感性分支；原范围单独保留，新增采样不是出生事实",
            ],
            artifact_ids=[],
            feature_ids=[],
        )
        rows.append(row)
    return rows

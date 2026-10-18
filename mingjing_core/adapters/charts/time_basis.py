"""L1 birth time conversion: fold/gap, explicit clock basis and no chosen school."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .adapter import stable_id
from .time_basis_solar import solar_time
from .time_basis_zones import load_zone


def _reported(day: str, reported_time: str) -> datetime:
    if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("出生日期需要明确阳历年月日")
    if not isinstance(reported_time, str) or not re.fullmatch(
        r"\d{2}:\d{2}(?::\d{2})?", reported_time
    ):
        raise ValueError("出生时刻需要明确钟表时分，可带秒")
    value = datetime.fromisoformat(day + "T" + reported_time)
    if not 1901 <= value.year <= 2099:
        raise ValueError("当前时间口径验证范围为1901至2099年")
    return value


def _clock_options(local: datetime, zone: ZoneInfo) -> list[dict[str, Any]]:
    options, seen = [], set()
    for fold in (0, 1):
        aware = local.replace(tzinfo=zone, fold=fold)
        utc = aware.astimezone(UTC)
        actual = utc.astimezone(zone)
        if actual.replace(tzinfo=None) != local or utc in seen:
            continue
        seen.add(utc)
        options.append({"utc": utc, "assumption": "clock", "fold": actual.fold})
    return options


def _standard_options(local: datetime, zone: ZoneInfo) -> list[dict[str, Any]]:
    offsets = {
        aware.utcoffset() - (aware.dst() or timedelta())
        for aware in (local.replace(tzinfo=zone, fold=fold) for fold in (0, 1))
    }
    output = []
    for offset in sorted(offsets):
        utc = (local - offset).replace(tzinfo=UTC)
        actual = utc.astimezone(zone)
        standard_offset = actual.utcoffset() - (actual.dst() or timedelta())
        if standard_offset == offset:
            output.append(
                {"utc": utc, "assumption": "already_standard", "fold": actual.fold}
            )
    return output


def _instant(
    item: dict[str, Any], zone: ZoneInfo, source: dict[str, Any], reported: datetime
) -> dict[str, Any]:
    utc = item["utc"]
    clock = utc.astimezone(zone)
    dst = clock.dst() or timedelta()
    standard_offset = clock.utcoffset() - dst
    standard = (utc + standard_offset).replace(tzinfo=None)
    return {
        "status": "valid",
        "utc": utc.isoformat().replace("+00:00", "Z"),
        "clock": clock.isoformat(),
        "standard": standard.isoformat(),
        "reported": reported.isoformat(),
        "timezone": zone.key,
        "offset_minutes": clock.utcoffset().total_seconds() / 60,
        "standard_offset_minutes": standard_offset.total_seconds() / 60,
        "dst_minutes": dst.total_seconds() / 60,
        "fold": clock.fold,
        "assumptions": [item["assumption"]],
        "timezone_source": source,
        "warnings": ["历史时区数据可能有误差，不能代替出生记录。"]
        if reported.year < 1949
        else [],
    }


def resolve_birth_instants(
    date: str, reported_time: str, place: dict[str, Any], clock_basis: str
) -> list[dict[str, Any]]:
    if clock_basis not in ("clock", "standard", "unknown"):
        raise ValueError("出生时间依据必须为clock/standard/unknown")
    if not isinstance(place, dict):
        raise ValueError("需要已确认的出生时区与地点，不能默认城市")
    local = _reported(date, reported_time)
    zone, provenance = load_zone(place.get("tz"))
    clock = _clock_options(local, zone)
    standard = _standard_options(local, zone)
    options = (
        clock
        if clock_basis == "clock"
        else standard
        if clock_basis == "standard"
        else clock + standard
    )
    by_utc: dict[str, dict[str, Any]] = {}
    for item in options:
        value = _instant(item, zone, provenance, local)
        if value["utc"] in by_utc:
            assumptions = by_utc[value["utc"]]["assumptions"]
            if item["assumption"] not in assumptions:
                assumptions.append(item["assumption"])
        else:
            by_utc[value["utc"]] = value
    result = [by_utc[key] for key in sorted(by_utc)]
    if not clock and clock_basis in ("clock", "unknown"):
        result.append(
            {
                "status": "nonexistent",
                "utc": None,
                "reported": local.isoformat(),
                "timezone": zone.key,
                "assumptions": ["clock"],
                "timezone_source": provenance,
                "warnings": [
                    "该钟表时刻在时区跳时中不存在，需要核对记录，不能自动平移一小时。"
                ],
            }
        )
    if not result:
        raise ValueError("该标准时坐标没有一致的历史时区解，需要核对时间依据")
    question = len(result) != 1 or any(row["status"] != "valid" for row in result)
    for row in result:
        row["requires_confirmation"] = question
        identity = {
            key: value for key, value in row.items() if key != "timezone_source"
        }
        row["id"] = stable_id(
            "instant-",
            [identity, provenance["zone_sha256"], provenance["iana_version"]],
        )
    return result


def time_basis_candidates(
    date: str,
    reported_time: str | None,
    place: dict[str, Any],
    clock_basis: str,
    *,
    precision: str = "reported",
) -> dict[str, Any]:
    from .time_basis_candidates import build_candidates

    return build_candidates(
        date, reported_time, place, clock_basis, precision=precision
    )


__all__ = ["resolve_birth_instants", "solar_time", "time_basis_candidates"]

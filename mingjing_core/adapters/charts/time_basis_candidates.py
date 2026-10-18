"""Pure declared-basis pillars; no scoring, persistence or school preference."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ...calculations.bazi.calendar_layers import solar_at
from .adapter import stable_id
from .time_basis import resolve_birth_instants
from .time_basis_solar import solar_time
from .worker import load_engine, version


def _jie(engine: Any, calendar: datetime) -> dict[str, Any]:
    lunar = solar_at(engine, calendar).getLunar()
    rows = [
        (item.getName(), datetime.fromisoformat(item.getSolar().toYmdHms()))
        for item in (lunar.getPrevJie(), lunar.getNextJie())
    ]
    name, boundary = min(rows, key=lambda row: abs((calendar - row[1]).total_seconds()))
    distance = abs((calendar - boundary).total_seconds())
    return {
        "uncertain": distance <= 120,
        "nearest_jie": name,
        "calendar_boundary": boundary.isoformat() + "+08:00",
        "distance_seconds": distance,
        "method": "physical_instant_UTC_plus8_not_solar_coordinate",
    }


def _candidate(
    instant: dict[str, Any], basis: str, solar: dict[str, Any], engine: Any
) -> dict[str, Any]:
    utc = datetime.fromisoformat(instant["utc"].replace("Z", "+00:00")).astimezone(UTC)
    calendar = (utc + timedelta(hours=8)).replace(tzinfo=None)
    coordinate = datetime.fromisoformat(solar[basis])
    physical = solar_at(engine, calendar).getLunar()
    local = solar_at(engine, coordinate).getLunar().getEightChar()
    local.setSect(1)
    offset = (
        8 if basis == "beijing_standard" else instant["standard_offset_minutes"] / 60
    )
    longitude = (
        offset * 15
        if basis in ("standard", "beijing_standard")
        else solar["longitude"] + solar["eot_minutes"] / 4
    )
    standard = datetime.fromisoformat(
        solar["beijing_standard"] if basis == "beijing_standard" else solar["standard"]
    )
    return {
        "basis": basis,
        "utc": instant["utc"],
        "instant_id": instant["id"],
        "coordinate_datetime": coordinate.isoformat(),
        "calendar_datetime": calendar.isoformat(),
        "civil_datetime": standard.strftime("%Y-%m-%d %H:%M"),
        "civil_datetime_basis": "standard_clock_minute_for_legacy_only_when_compatible; exact UTC is authoritative",
        "timezone_offset": offset,
        "engine_longitude": longitude,
        "engine_longitude_role": "effective_meridian_not_geographic_birth_longitude",
        "legacy_args_compatible": -180 <= longitude <= 180
        and standard.second == 0
        and standard.microsecond == 0,
        "pillars": {
            "year": physical.getYearInGanZhiExact(),
            "month": physical.getMonthInGanZhiExact(),
            "day": local.getDay(),
            "hour": local.getTime(),
        },
        "pillar_method": {
            "year_month": "physical_UTC_plus8_exact_jie",
            "day_hour": "declared_coordinate_sect1_late_zi",
            "day_boundary": "23:00_advances_day",
            "subsecond_handling": "floor_to_engine_second",
        },
        "solar_time": solar,
        "jie_uncertainty": _jie(engine, calendar),
        "assumptions": instant["assumptions"],
        "requires_confirmation": instant["requires_confirmation"],
        "timezone_source": instant["timezone_source"],
        "engine_versions": {"lunar-python": version("lunar-python")},
    }


def _reported_samples(reported_time: str | None, precision: str) -> list[str]:
    if precision == "reported":
        if reported_time is None:
            raise ValueError("已报告时刻模式需要明确时分")
        return [reported_time]
    if precision != "unknown":
        raise ValueError("时间基础层只接受reported或unknown，区间由调用方逐点传入")
    minutes = {hour * 60 for hour in range(0, 24, 2)}
    minutes.update(hour * 60 + delta for hour in range(1, 24, 2) for delta in (-1, 1))
    return [f"{minute // 60:02d}:{minute % 60:02d}" for minute in sorted(minutes)]


def _deduplicate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row["pillars"][name] for name in ("day", "hour", "month"))
        if key not in grouped:
            grouped[key] = dict(
                row,
                id=stable_id("time-basis-", ["p8-time-basis-v1", key]),
                basis_options=[],
                source_variants=[],
            )
        group = grouped[key]
        if row["basis"] not in group["basis_options"]:
            group["basis_options"].append(row["basis"])
        group["source_variants"].append(row)
        group["requires_confirmation"] |= row["requires_confirmation"]
        group["representative_only_not_chosen_school"] = True
    return list(grouped.values())


def build_candidates(
    date: str,
    reported_time: str | None,
    place: dict[str, Any],
    clock_basis: str,
    *,
    precision: str,
    include_beijing: bool = False,
) -> dict[str, Any]:
    if not isinstance(place, dict) or "lon" not in place:
        raise ValueError("必须提供已确认经度和IANA时区，不能默认出生地")
    engine, rows, instants = load_engine("bazi"), [], []
    for sample in _reported_samples(reported_time, precision):
        resolved = resolve_birth_instants(date, sample, place, clock_basis)
        instants += resolved
        for instant in resolved:
            if instant["status"] != "valid":
                continue
            solar = solar_time(instant, place["lon"])
            bases = (
                ("standard", "true_solar", "beijing_standard")
                if include_beijing
                else ("standard", "true_solar")
            )
            rows += [_candidate(instant, basis, solar, engine) for basis in bases]
    items = _deduplicate(rows)
    hour_stable = bool(items) and len({row["pillars"]["hour"] for row in items}) == 1
    return {
        "version": "p8-time-basis-v1",
        "items": items,
        "instants": instants,
        "hour_pillar_stable": hour_stable,
        "all_pillars_stable": len(items) == 1,
        "conclusion": "时柱稳定，无需按时柱校正"
        if hour_stable
        else "时间口径或时刻仍有不同候选",
        "requires_confirmation": len(items) > 1
        or any(row["requires_confirmation"] for row in instants),
        "selected_basis": None,
        "sampling": "reported_point"
        if precision == "reported"
        else "36_clock_samples_not_continuous_coverage",
        "limits": [
            "没有选择默认流派；首条只是代表项，source_variants保留全部来源。",
            "同柱组合去重不证明大运起运或紫微对所有来源时刻一致，调用方须保留来源分支。",
            "仅纯计算；不确认出生资料，不输出前三或命理得分。",
        ],
        "model_calls": 0,
        "writes": 0,
    }

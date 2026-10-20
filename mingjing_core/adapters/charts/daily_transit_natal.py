"""Reusable worker-local natal state; explicit dates and one physical instant."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from .astro_ephemeris import Ephemeris, actual_utc
from .time_basis import time_basis_candidates
from .time_basis_chart import bazi_context
from .time_basis_request import validate_request
from .worker import load_engine

BEIJING = timezone(timedelta(hours=8))
SCOPE_KEYS = ("owner_user_id", "subject_id", "revision", "operation_id")


def snapshot(day: str, birth_day: str | None = None) -> datetime:
    if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
        raise ValueError("daily_transit_date_invalid")
    try:
        value = date.fromisoformat(day)
    except ValueError:
        raise ValueError("daily_transit_date_invalid") from None
    if not 1901 <= value.year <= 2099:
        raise ValueError("daily_transit_date_out_of_range")
    if birth_day is not None and value < date.fromisoformat(birth_day):
        raise ValueError("daily_transit_before_birth")
    return datetime(value.year, value.month, value.day, 12, tzinfo=BEIJING)


@dataclass(frozen=True)
class PreparedNatal:
    request: dict[str, Any]
    candidate: dict[str, Any]
    basis_comparisons: list[dict[str, Any]]
    bazi_engine: Any
    bazi_data: dict[str, Any]
    ziwei_engine: Any
    ziwei_ast: Any
    ziwei_natal: dict[str, Any]
    ephemeris: Ephemeris
    natal_planets: dict[str, Any]


def _basis(request: dict[str, Any]) -> tuple[dict, list[dict]]:
    birth = request["birth"]
    result = time_basis_candidates(
        birth["date"],
        birth.get("reported_time"),
        birth.get("place"),
        birth.get("clock_basis"),
        precision="reported",
        include_beijing=True,
    )
    if len(result["instants"]) != 1 or any(
        row["status"] != "valid" or row["requires_confirmation"]
        for row in result["instants"]
    ):
        raise ValueError("daily_transit_unconfirmed_physical_instant")
    variants = [row for item in result["items"] for row in item["source_variants"]]
    primary = next(row for row in variants if row["basis"] == "true_solar")
    comparisons = [row for row in variants if row["basis"] == "beijing_standard"]
    return primary, comparisons


def _ziwei(engine: Any, candidate: dict, gender: str) -> tuple[Any, dict]:
    coordinate = datetime.fromisoformat(candidate["coordinate_datetime"])
    ast, corrected = engine.build(coordinate, 0, gender, 0)
    ziwei = engine.natal(ast, corrected)
    ziwei["time_basis"] = candidate["basis"]
    ziwei["method"].update(
        input="preconverted_coordinate_no_second_longitude_or_DST_adjustment",
        equation_of_time_applied=candidate["basis"] == "true_solar",
    )
    return ast, ziwei


def _comparisons(
    primary: dict, candidates: list[dict], native: dict, engine: Any, gender: str
) -> list[dict]:
    comparisons = []
    fields = ("lunar_date", "ming_gong", "shen_gong", "palaces", "wuxing_ju")
    for candidate in candidates:
        _, alternate = _ziwei(engine, candidate, gender)
        changed = ["bazi.pillars"] if candidate["pillars"] != primary["pillars"] else []
        changed += [
            "ziwei." + field for field in fields if native[field] != alternate[field]
        ]
        if changed:
            comparisons.append(
                dict(candidate, fields_changed=changed, ziwei_natal=alternate)
            )
    return comparisons


def prepare_natal(natal: dict[str, Any], day: str) -> PreparedNatal:
    if not isinstance(natal, dict):
        raise ValueError("daily_transit_natal_object_required")
    snapshot(day)
    request = dict(deepcopy(natal), as_of_date=day)
    validate_request(request)
    candidate, candidates = _basis(request)
    bazi_engine, ziwei_engine = load_engine("bazi"), load_engine("ziwei")
    gender = request["birth"]["gender"]
    ast, ziwei = _ziwei(ziwei_engine, candidate, gender)
    comparisons = _comparisons(candidate, candidates, ziwei, ziwei_engine, gender)
    ephemeris = Ephemeris()
    _, jd = ephemeris.julian(actual_utc(candidate["utc"]))
    return PreparedNatal(
        request=request,
        candidate=candidate,
        basis_comparisons=comparisons,
        bazi_engine=bazi_engine,
        bazi_data=bazi_context(candidate, request),
        ziwei_engine=ziwei_engine,
        ziwei_ast=ast,
        ziwei_natal=ziwei,
        ephemeris=ephemeris,
        natal_planets=ephemeris.planets(jd),
    )


def utc_string(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

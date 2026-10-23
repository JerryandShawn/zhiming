"""Compose deterministic supplements from one already-computed time branch."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .calendar_layers import calendar_layers, decade_luck, month_command
from .elements import block, ten_gods, validate_pillars
from .stars import auxiliary_stars
from .strength import scores
from .structure import climate, patterns, useful


def supplement(engine: Any, args: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    pillars = {key: value["ganzhi"] for key, value in data["pillars"].items()}
    validate_pillars(pillars)
    civil = datetime.strptime(args["datetime"], "%Y-%m-%d %H:%M")
    calendar = civil + timedelta(hours=8 - args["tz"])
    strength = scores(pillars)
    pattern = patterns(pillars, strength)
    climatic = climate(pillars["day"][0], pillars["month"][1])
    return block(
        "p8-opt-in-bazi-supplement-v1",
        "各块独立登记来源与口径；不替代v3原始产物",
        scope="bazi_and_daily_calculation_only",
        ten_gods=ten_gods(pillars),
        month_command=month_command(engine, calendar, pillars["month"][1], pillars["day"][0]),
        strength=strength,
        patterns=pattern,
        climate=climatic,
        useful_candidates=useful(pillars, strength, pattern, climatic),
        decade_luck=decade_luck(engine, calendar, 1 if args["gender"] in ("男", "male", "m", "M", "1") else 0, pillars),
        calendar_layers=calendar_layers(engine, int(args["date"][:4]), args["date"], pillars),
        auxiliary_stars=auxiliary_stars(pillars),
        interpretation_status="calculation_only_no_published_interpretation_rules",
    )

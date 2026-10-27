"""Few synthetic near-boundary probes; differences are observations, not product failures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ....calculations.bazi.calendar_layers import solar_at
from ..time_basis_solar import equation_of_time
from ..worker import load_engine
from .night24_solar_reference import SwissReference, iso

CASES = (
    ("2026-02-11T01:00:00", 87.625),
    ("2026-11-03T23:00:00", 104.07),
    ("2026-02-11T00:00:00", 120.0),
    ("2026-11-03T01:00:00", 121.565),
    ("2000-06-21T23:00:00", 179.9),
    ("2000-12-21T00:00:00", -179.9),
)
OFFSETS_SECONDS = (-30, -5, -1, 0, 1, 5, 30)


def _anchor(coordinate: datetime, longitude: float) -> datetime:
    guess = coordinate.replace(tzinfo=UTC) - timedelta(minutes=4 * longitude)
    for _ in range(8):
        guess = coordinate.replace(tzinfo=UTC) - timedelta(
            minutes=4 * longitude + equation_of_time(guess)
        )
    return guess.replace(microsecond=0)


def _pillars(engine: Any, coordinate: datetime) -> dict[str, str]:
    eight = solar_at(engine, coordinate).getLunar().getEightChar()
    eight.setSect(1)
    return {"day": eight.getDay(), "hour": eight.getTime()}


def _probe(
    engine: Any,
    reference: SwissReference,
    target: datetime,
    longitude: float,
    anchor: datetime,
    offset: int,
) -> dict[str, Any]:
    moment = anchor + timedelta(seconds=offset)
    sample = reference.compare(moment)
    noaa = moment.replace(tzinfo=None) + timedelta(
        minutes=4 * longitude + sample["noaa_eot_minutes"]
    )
    swiss = moment.replace(tzinfo=None) + timedelta(
        seconds=240 * longitude
        + 60 * sample["swiss_eot_at_UT1_minutes"]
        + sample["swiss_inferred_UT1_minus_UTC_seconds"],
    )
    noaa_pillars, swiss_pillars = _pillars(engine, noaa), _pillars(engine, swiss)
    return {
        "nominal_apparent_boundary": target.isoformat(),
        "longitude": longitude,
        "offset_from_floor_UTC_anchor_seconds": offset,
        "actual_UTC": iso(moment),
        "noaa_apparent_coordinate": noaa.isoformat(),
        "swiss_apparent_coordinate": swiss.isoformat(),
        "noaa_distance_from_boundary_seconds": (noaa - target).total_seconds(),
        "swiss_distance_from_boundary_seconds": (swiss - target).total_seconds(),
        "noaa_day_hour": noaa_pillars,
        "swiss_day_hour": swiss_pillars,
        "same_day_hour": noaa_pillars == swiss_pillars,
        "eot_difference_seconds": sample["noaa_minus_swiss_eot_seconds"],
        "coordinate_difference_seconds": sample[
            "noaa_minus_swiss_apparent_clock_seconds"
        ],
        "swiss_inferred_UT1_minus_UTC_seconds": sample[
            "swiss_inferred_UT1_minus_UTC_seconds"
        ],
    }


def boundary_probes(reference: SwissReference) -> dict[str, Any]:
    engine, rows = load_engine("bazi"), []
    for coordinate, longitude in CASES:
        target = datetime.fromisoformat(coordinate)
        anchor = _anchor(target, longitude)
        rows += [
            _probe(engine, reference, target, longitude, anchor, offset)
            for offset in OFFSETS_SECONDS
        ]
    controls = [
        row for row in rows if abs(row["offset_from_floor_UTC_anchor_seconds"]) == 30
    ]
    return {
        "case_count": len(CASES),
        "probe_count": len(rows),
        "day_hour_disagreements": sum(not row["same_day_hour"] for row in rows),
        "day_pillar_disagreements": sum(
            row["noaa_day_hour"]["day"] != row["swiss_day_hour"]["day"] for row in rows
        ),
        "hour_pillar_disagreements": sum(
            row["noaa_day_hour"]["hour"] != row["swiss_day_hour"]["hour"]
            for row in rows
        ),
        "thirty_second_control_disagreements": sum(
            not row["same_day_hour"] for row in controls
        ),
        "comparison": (
            "same lunar-python sect1/floor-to-second pillar engine, two solar clock inputs; "
            "not independent pillar validation"
        ),
        "anchor": "NOAA coordinate root iterated eight times, then actual UTC floored to an input second",
        "rows": rows,
    }

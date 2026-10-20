"""Real two-sided sensitivity samples; hypothetical clocks never replace birth facts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ...calculations.bazi.calendar_layers import solar_at
from .time_basis_solar import equation_of_time

SCHOOL = "p8-true-solar-day-hour-sect1; physical-UTC+8-exact-jie-year-month"
LUNAR_SOURCE = (
    "https://github.com/6tail/lunar-python/blob/v1.4.8/lunar_python/EightChar.py"
)


def solar_coordinate(utc: datetime, longitude: float) -> datetime:
    return utc.astimezone(UTC).replace(tzinfo=None) + timedelta(
        minutes=4 * longitude + equation_of_time(utc)
    )


def coordinate_to_utc(coordinate: datetime, longitude: float) -> datetime:
    guess = coordinate.replace(tzinfo=UTC) - timedelta(minutes=4 * longitude)
    if guess.year < 1901:
        guess = datetime(1901, 1, 1, tzinfo=UTC)
    elif guess.year > 2099:
        guess = datetime(2099, 12, 31, 23, 59, 59, tzinfo=UTC)
    for _ in range(8):
        if not 1901 <= guess.year <= 2099:
            raise ValueError("boundary_sample_outside_verified_utc_range")
        guess = coordinate.replace(tzinfo=UTC) - timedelta(
            minutes=4 * longitude + equation_of_time(guess)
        )
    return guess


def pillars_at(
    engine: Any, utc: datetime, coordinate: datetime, sect: int = 1
) -> dict[str, str]:
    physical = (utc.astimezone(UTC) + timedelta(hours=8)).replace(tzinfo=None)
    lunar = solar_at(engine, physical).getLunar()
    eight = solar_at(engine, coordinate).getLunar().getEightChar()
    eight.setSect(sect)
    return {
        "year": lunar.getYearInGanZhiExact(),
        "month": lunar.getMonthInGanZhiExact(),
        "day": eight.getDay(),
        "hour": eight.getTime(),
    }


def sample_at(
    engine: Any, utc: datetime, coordinate: datetime, label: str, *, sect: int = 1
) -> dict[str, Any]:
    return {
        "label": label,
        "is_birth_fact": False,
        "physical_utc": utc.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "coordinate_datetime": coordinate.isoformat(),
        "coordinate_basis": "true_solar",
        "pillars": pillars_at(engine, utc, coordinate, sect),
        "school": SCHOOL
        if sect == 1
        else "lunar-python-sect2-midnight-day-comparison-only",
        "day_boundary": "23:00_advances_day" if sect == 1 else "00:00_advances_day",
        "source": LUNAR_SOURCE,
        "subsecond_handling": "floor_to_engine_second",
    }


def clock_sides(
    engine: Any, boundary: datetime, longitude: float, *, midnight: bool
) -> list[dict[str, Any]]:
    rows = []
    for label, direction in (("before", -1), ("after", 1)):
        coordinate = boundary + timedelta(seconds=direction)
        try:
            utc = coordinate_to_utc(coordinate, longitude)
        except ValueError as error:
            if str(error) != "boundary_sample_outside_verified_utc_range":
                raise
            rows.append(
                {
                    "label": label,
                    "status": "not_computed_outside_verified_utc_range",
                    "is_birth_fact": False,
                    "coordinate_datetime": coordinate.isoformat(),
                    "pillars": None,
                    "error_code": str(error),
                    "source": LUNAR_SOURCE,
                    "school": SCHOOL,
                }
            )
            continue
        rows.append(sample_at(engine, utc, coordinate, label))
        if midnight:
            rows.append(sample_at(engine, utc, coordinate, label + "_sect2", sect=2))
    return rows


def jie_sides(
    engine: Any, boundary: datetime, longitude: float
) -> list[dict[str, Any]]:
    rows = []
    for label, direction in (("before", -1), ("after", 1)):
        utc = boundary.astimezone(UTC) + timedelta(seconds=direction)
        rows.append(sample_at(engine, utc, solar_coordinate(utc, longitude), label))
    return rows

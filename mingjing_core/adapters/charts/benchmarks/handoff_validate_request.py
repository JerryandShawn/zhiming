"""Input binding for the builder's fixed synthetic fixture, never a generic API."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .handoff_build import BIRTH, TARGET
from .handoff_refs import digest

CANONICAL_UTC = "1994-03-12T00:20:00Z"
CANONICAL_SCALE = "natal_with_explicit_target_layers"


def canonical_fixture_request(preview: dict) -> None:
    """Native time-basis documents do not echo every original birth field."""
    request = preview["request"]
    if (
        digest(request["birth"]) != digest(BIRTH)
        or request["target_date"] != TARGET
        or request["time_scale"] != CANONICAL_SCALE
        or request["physical_birth_at_utc"] != CANONICAL_UTC
    ):
        raise ValueError("preview_canonical_fixture_request_required")


def basis_target(chart: dict, preview: dict) -> None:
    target = preview["request"]["target_date"]
    layers = chart["data"]["p8"]["calendar_layers"]
    if (
        layers["day"]["date"] != target
        or type(layers["requested_gregorian_year"]) is not int
        or layers["requested_gregorian_year"] != int(target[:4])
    ):
        raise ValueError("preview_basis_target_mismatch")


def _coordinates(longitude, latitude, preview: dict) -> None:
    place = preview["request"]["birth"]["place"]
    if (
        type(longitude) not in (int, float)
        or type(latitude) not in (int, float)
        or longitude != place["lon"]
        or latitude != place["lat"]
    ):
        raise ValueError("preview_astro_input_coordinates_mismatch")


def astro_profile_inputs(profile: dict, preview: dict) -> None:
    request, values = preview["request"], profile["input"]
    birth = request["birth"]
    declared = values["declared_birth"]
    expected_civil = birth["date"] + " " + birth["reported_time"]
    if (
        values["target_date"] != request["target_date"]
        or declared["solar_datetime"] != expected_civil
        or values["sample_civil_datetime"] != expected_civil
        or declared["calendar"] != "solar"
        or values["calendar"] != "solar"
        or type(declared["timezone_offset"]) not in (int, float)
        or type(values["timezone_offset"]) not in (int, float)
        or declared["timezone_offset"] != values["timezone_offset"]
    ):
        raise ValueError("preview_astro_declared_input_mismatch")
    _coordinates(values["longitude"], values["latitude"], preview)
    _coordinates(declared["location"]["lng"], declared["location"]["lat"], preview)


def timing_inputs(data: dict, preview: dict, utc: Callable[[str], datetime]) -> None:
    target = preview["request"]["target_date"]
    if data["version"] == "p8-secondary-progressions-v1":
        if utc(data["actual_UTC"]["target_at"]) != utc(target + "T00:00:00Z"):
            raise ValueError("preview_progression_target_mismatch")
    elif data["version"] == "p8-solar-return-v1":
        if type(data["return_year"]) is not int or data["return_year"] != int(
            target[:4]
        ):
            raise ValueError("preview_return_year_mismatch")
        location = data["houses"]["location"]
        _coordinates(location["longitude"], location["latitude"], preview)
    else:
        raise ValueError("preview_timing_input_binding_unavailable")

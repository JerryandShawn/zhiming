"""Inject existing isolated P8 calculation artifacts; never infer missing geography."""

from __future__ import annotations

from typing import Any

from ..p8_adapter import P8ChartAdapter
from .records import BirthMetadata, CalculationInputs, fingerprint


class P8Engine:
    def __init__(
        self, python: str, inputs: dict[str, CalculationInputs], target_date: str
    ) -> None:
        self.adapter = P8ChartAdapter("e2-local-synthetic", python=python)
        self.inputs = inputs
        self.target_date = target_date
        self.cache: dict[str, dict[str, Any]] = {}

    def __call__(self, birth: BirthMetadata) -> dict[str, Any]:
        key = fingerprint(birth.public_input())
        if key in self.cache:
            return self.cache[key]
        if key not in self.inputs:
            raise ValueError("chart_missing_verified_coordinates_offset_or_precision")
        coordinates = self.inputs[key]
        fields = (birth.year, birth.month, birth.day, birth.hour, birth.minute)
        if any(value is None for value in fields) or birth.gender is None:
            raise ValueError("chart_birth_fields_incomplete")
        if birth.calendar != "solar" or birth.approximate is True:
            raise ValueError("chart_requires_explicit_solar_minute_input")
        civil = (
            f"{birth.year:04}-{birth.month:02}-{birth.day:02} "
            f"{birth.hour:02}:{birth.minute:02}"
        )
        archive = {
            "user": {
                "gender": birth.gender,
                "birth": {
                    "solar_datetime": civil,
                    "time_precision": "exact",
                    "calendar": "solar",
                    "timezone_offset": coordinates.timezone_offset,
                    "location": {"lng": coordinates.longitude},
                    "input_status": {
                        "source": coordinates.provenance,
                        "scope": "benchmark_not_user_profile",
                    },
                },
            }
        }
        result = self.adapter.calculate(
            archive, self.target_date, ["bazi"], 0, "e2-synthetic-" + key[:12]
        )
        if result["errors"] or not result["artifacts"]:
            raise RuntimeError("e2_isolated_chart_failed_without_fallback")
        value = {
            "artifacts": result["artifacts"],
            "profiles": result["profiles"],
            "features": result["features"],
        }
        self.cache[key] = value
        return value

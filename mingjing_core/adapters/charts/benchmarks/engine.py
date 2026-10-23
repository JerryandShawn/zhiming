"""Inject existing isolated P8 calculation artifacts; never infer missing geography."""

from __future__ import annotations

from typing import Any

from ..p8_adapter import P8ChartAdapter
from .annual_v2 import annual_basis, annual_view
from .eligibility_v2 import YearReview, question_year
from .records import BirthMetadata, CalculationInputs, Question, fingerprint


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
        value = self._calculate(birth, self.target_date, "e2-synthetic-" + key[:12])
        self.cache[key] = value
        return value

    def for_question(
        self, record: Question, *, review: YearReview | None = None
    ) -> dict[str, Any]:
        decision = question_year(record, review)
        if decision.year is None:
            raise ValueError("question_chart_requires_explicit_target_year")
        basis = annual_basis(decision.year)
        birth_key = fingerprint(record.birth.public_input())
        key = fingerprint([birth_key, decision.year, basis["method"]])
        if key not in self.cache:
            computed = self._calculate(
                record.birth, basis["sampling_date"], "e2-annual-" + key[:12]
            )
            value = annual_view(computed, decision.year)
            value["benchmark_birth_fingerprint"] = birth_key
            self.cache[key] = value
        return self.cache[key]

    def _calculate(
        self, birth: BirthMetadata, target_date: str, subject_id: str
    ) -> dict[str, Any]:
        key = fingerprint(birth.public_input())
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
        result = self.adapter.calculate(archive, target_date, ["bazi"], 0, subject_id)
        if result["errors"] or not result["artifacts"]:
            raise RuntimeError("e2_isolated_chart_failed_without_fallback")
        value = {
            "artifacts": result["artifacts"],
            "profiles": result["profiles"],
            "features": result["features"],
        }
        return value

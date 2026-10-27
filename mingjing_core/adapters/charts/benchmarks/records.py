"""Normalized E2 records keep the answer key outside inference inputs."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


def fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class BirthMetadata:
    year: int | None
    month: int | None
    day: int | None
    hour: int | None
    minute: int | None
    gender: str | None
    location: str | None
    calendar: str | None
    approximate: bool | None = None

    def __post_init__(self) -> None:
        bounds = {
            "year": (1, 9999),
            "month": (1, 12),
            "day": (1, 31),
            "hour": (0, 23),
            "minute": (0, 59),
        }
        for name, (lower, upper) in bounds.items():
            value = getattr(self, name)
            if value is not None and (
                type(value) is not int or not lower <= value <= upper
            ):
                raise ValueError("invalid_birth_" + name)
        if (
            all(getattr(self, name) is not None for name in ("year", "month", "day"))
            and self.calendar == "solar"
        ):
            datetime(self.year, self.month, self.day)  # type: ignore[arg-type]
        if self.gender not in (None, "男", "女"):
            raise ValueError("invalid_birth_gender")
        if self.approximate is not None and type(self.approximate) is not bool:
            raise ValueError("invalid_birth_precision")

    def public_input(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Question:
    id: str
    case_id: str
    text: str
    options: tuple[tuple[str, str], ...]
    answer: str
    birth: BirthMetadata
    source: str
    category: str | None = None
    competition_year: int | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.case_id or not self.text.strip():
            raise ValueError("question_identity_or_text_missing")
        if tuple(letter for letter, _ in self.options) != tuple("ABCD"):
            raise ValueError("expected_four_ordered_options")
        if any(
            not isinstance(text, str) or not text.strip() for _, text in self.options
        ):
            raise ValueError("option_text_missing")
        if self.answer not in tuple("ABCD"):
            raise ValueError("answer_not_in_options")

    def public_input(self) -> dict[str, Any]:
        return {
            "question_id": self.id,
            "question": self.text,
            "options": dict(self.options),
        }

    def scoring_fingerprint(self) -> str:
        # Birth is deliberately excluded so a declared placebo remains paired.
        return fingerprint(
            [
                self.source,
                self.id,
                self.case_id,
                self.text,
                self.options,
                self.answer,
                self.competition_year,
            ]
        )


@dataclass(frozen=True)
class CalculationInputs:
    longitude: float
    timezone_offset: float
    provenance: str
    minute_precision_accepted: bool

    def __post_init__(self) -> None:
        for value, lower, upper in (
            (self.longitude, -180, 180),
            (self.timezone_offset, -14, 14),
        ):
            if (
                isinstance(value, bool)
                or not math.isfinite(value)
                or not lower <= value <= upper
            ):
                raise ValueError("invalid_calculation_coordinates")
        if not self.provenance.strip() or self.minute_precision_accepted is not True:
            raise ValueError("explicit_calculation_input_provenance_required")

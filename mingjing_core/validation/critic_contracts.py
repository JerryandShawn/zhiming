"""Strict v2 critique contracts; severity belongs to code, never to the model."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

Item = Literal[
    "E1", "E2", "E3", "E4", "E5", "J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9"
]
CalibrationState = Literal["revision_enabled", "record_only"]
ITEM_TYPES = MappingProxyType(
    {
        "E1": "time_error",
        "E2": "false_receipt",
        "E3": "unsupported_chart",
        "E4": "chart_inconsistency",
        "E5": "memory_error",
        "J1": "fatalism",
        "J2": "unsafe_advice",
        "J3": "generic_barnum",
        "J4": "sycophancy",
        "J5": "off_topic",
        "J6": "fabrication",
        "J7": "overpromise",
        "J8": "over_asking",
        "J9": "tone",
    }
)
SEVERITIES = MappingProxyType(
    {
        "E1": 5,
        "E2": 5,
        "E3": 4,
        "E4": 3,
        "E5": 4,
        "J1": 4,
        "J2": 5,
        "J3": 3,
        "J4": 3,
        "J5": 4,
        "J6": 5,
        "J7": 3,
        "J8": 2,
        "J9": 2,
    }
)
CRITIC_PROMPT_VERSION = "2.1.0"
RUBRIC_VERSION = "v2.1.0"


class CriticIssue(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )

    item: Item
    type: StrictStr
    quote: StrictStr = Field(min_length=1, max_length=20_000, repr=False)
    rule: StrictStr = Field(min_length=1, max_length=2_000, repr=False)
    evidence: StrictStr = Field(max_length=200, repr=False)
    fix_hint: StrictStr = Field(min_length=1, max_length=2_000, repr=False)
    confidence: StrictInt = Field(ge=1, le=3)

    @model_validator(mode="after")
    def validate_atomic_item(self) -> Self:
        if self.type != ITEM_TYPES[self.item]:
            raise ValueError("item and type do not match")
        if not self.quote.strip() or not self.rule.strip() or not self.fix_hint.strip():
            raise ValueError("issue text cannot be blank")
        if self.item.startswith("E") and not self.evidence.strip():
            raise ValueError("evidence item requires an evidence reference")
        return self


class CriticOutput(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )

    issues: tuple[CriticIssue, ...] = Field(max_length=14, repr=False)

    @model_validator(mode="after")
    def validate_unique_items(self) -> Self:
        if len({issue.item for issue in self.issues}) != len(self.issues):
            raise ValueError("each binary rubric item may appear only once")
        return self


@dataclass(frozen=True)
class ProgramIssue:
    item: Item
    quote: str = field(repr=False)
    rule: str = field(repr=False)
    evidence: str = field(repr=False)
    fix_hint: str = field(repr=False)
    resolved: bool = False

    def __post_init__(self) -> None:
        if self.item not in SEVERITIES or not self.item.startswith("E"):
            raise ValueError("program evidence findings must use E1-E5")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.quote, self.rule, self.evidence, self.fix_hint)
        ):
            raise ValueError(
                "program finding requires an observable quote, rule and evidence"
            )
        if type(self.resolved) is not bool:
            raise ValueError("program finding resolved flag must be boolean")


@dataclass(frozen=True)
class ParseResult:
    output: CriticOutput = field(repr=False)
    attempts: int
    parse_failed: bool
    error_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewIssue:
    item: Item
    type: str
    severity: int
    confidence: int
    quote: str = field(repr=False)
    rule: str = field(repr=False)
    evidence: str = field(repr=False)
    fix_hint: str = field(repr=False)
    source: Literal["critic", "program"]
    triggered: bool
    reason: str

    def as_dict(self) -> dict[str, str | int | bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class ReviewResult:
    verdict: Literal["pass", "revise"]
    mode: Literal["full", "evidence_only"]
    revision_action: Literal["none", "revise"]
    issues: tuple[ReviewIssue, ...] = field(repr=False)
    sample_queue: tuple[ReviewIssue, ...] = field(repr=False)
    critic_prompt_version: str
    calibration_version: str | None
    parse_failed: bool
    parse_attempts: int

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "mode": self.mode,
            "revision_action": self.revision_action,
            "issues": [issue.as_dict() for issue in self.issues],
            "sample_queue": [issue.as_dict() for issue in self.sample_queue],
            "critic_prompt_version": self.critic_prompt_version,
            "calibration_version": self.calibration_version,
            "parse_failed": self.parse_failed,
            "parse_attempts": self.parse_attempts,
        }

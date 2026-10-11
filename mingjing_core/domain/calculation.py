"""Calculation contracts; a computed feature is not an event or a prediction."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class CalculationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    system: Literal["bazi", "ziwei", "astro"]
    school_id: str
    owner_user_id: str
    subject_id: str
    revision: int
    branch_id: str
    input: dict[str, Any]
    requested_method: dict[str, Any]
    actual_method: dict[str, Any]
    versions: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    fallback: list[dict[str, Any]] = Field(default_factory=list)


class CalculationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    system: Literal["bazi", "ziwei", "astro"]
    school_id: str
    owner_user_id: str
    subject_id: str
    revision: int
    branch_id: str
    profile_id: str
    time_scale: str
    target_date: str
    data: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class CalculationFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    feature_key: str
    value: Any
    artifact_id: str
    path: str
    owner_user_id: str
    subject_id: str
    revision: int
    branch_id: str
    time_scale: str
    # Equality in a few samples is never continuous interval coverage.
    stability: Literal["exact_input", "sampled_stable", "conditional", "unknown"] = "unknown"


class TimeBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    owner_user_id: str
    subject_id: str
    revision: int
    input_precision: Literal["exact", "approximate", "interval", "unknown"]
    civil_datetime: str
    coverage: Literal["exact_input", "sampled_not_continuous"]
    confirmed_birth_time: bool = False
    sampling_range: dict[str, Any] | None = None
    feature_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

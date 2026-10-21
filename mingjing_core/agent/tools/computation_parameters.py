"""Model-facing intent only; authority and birth values come from application state."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from mingjing_core.agent.tools.parameters import Parameters
from mingjing_core.domain.consultation import ProfileField


class ChartCompute(Parameters):
    system: Literal["bazi", "ziwei", "astro"]
    target: str = Field(description="绝对日期YYYY-MM-DD；不能填写相对日期或自行提供出生资料")
    scale: Literal["natal", "daily", "monthly", "yearly"] = "natal"

    @field_validator("target")
    @classmethod
    def absolute_target(cls, value: str) -> str:
        if len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError("目标日期必须为YYYY-MM-DD")
        return value


class DateCalc(Parameters):
    operation: Literal["add_days", "difference"]
    start_date: str
    end_date: str | None = None
    days: int | None = Field(default=None, ge=-36600, le=36600)

    @field_validator("start_date", "end_date")
    @classmethod
    def absolute_date(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 10 or date.fromisoformat(value).isoformat() != value):
            raise ValueError("日期必须为YYYY-MM-DD")
        return value

    @model_validator(mode="after")
    def operation_arguments(self) -> DateCalc:
        if self.operation == "add_days" and (self.days is None or self.end_date is not None):
            raise ValueError("日期加日只接受days")
        if self.operation == "difference" and (self.end_date is None or self.days is not None):
            raise ValueError("日期差只接受end_date")
        return self


class MemoryUpdate(Parameters):
    fact_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)
    message_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=3000)
    summary: str = Field(min_length=1, max_length=1000)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)


class ProfileUpdateRequest(Parameters):
    fields: list[ProfileField] = Field(min_length=1, max_length=14)
    message_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=3000)

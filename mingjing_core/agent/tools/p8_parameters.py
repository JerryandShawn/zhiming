"""P8 tool intents never accept birth values, owner scope or consent."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .parameters import Parameters


class Almanac(Parameters):
    date: str

    @field_validator("date")
    @classmethod
    def absolute_date(cls, value: str) -> str:
        if (
            len(value) != 10
            or date.fromisoformat(value).isoformat() != value
            or not 1901 <= date.fromisoformat(value).year <= 2099
        ):
            raise ValueError("需要1901至2099年的绝对日期YYYY-MM-DD")
        return value


class DailyTransit(Almanac):
    """Daily snapshots share the same absolute-date-only argument contract."""


class WindowSearch(Parameters):
    start_date: str
    end_date: str
    purpose: Literal["签约", "面试", "搬家", "出行", "表白", "开业"]
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=31, ge=1, le=31)

    @model_validator(mode="after")
    def native_range(self) -> WindowSearch:
        for value in (self.start_date, self.end_date):
            Almanac(date=value)
        if not 0 <= (date.fromisoformat(self.end_date) - date.fromisoformat(self.start_date)).days < 366:
            raise ValueError("择日区间需要有序且最多366日")
        return self


class Synastry(Parameters):
    other_subject_id: str = Field(min_length=1, max_length=200)
    kind: Literal["romantic", "friendship", "collaboration"]

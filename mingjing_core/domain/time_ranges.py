"""Mainline U4 integration contract; no relative-language implementation here."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mingjing_core.domain.json_values import ensure_finite_json


class TimeRangeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start: datetime | None = None
    end: datetime | None = None
    granularity: str = "unknown"
    kind: Literal["point", "range", "recurring"] = "range"
    confidence: float = Field(default=0.0, ge=0, le=1)
    candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    needs_clarification: bool = True
    normalized_text: str = ""

    @model_validator(mode="after")
    def aware_range(self) -> TimeRangeResult:
        ensure_finite_json(self.candidates)
        for value in (self.start, self.end):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("时间范围必须带时区")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("时间范围顺序无效")
        return self


class TimeRangeParser(Protocol):
    def parse_time_range(
        self, text: str, ref_time: datetime, tz: str = "Asia/Shanghai", calendar: Any = None
    ) -> TimeRangeResult: ...


class UnavailableTimeRangeParser:
    """Explicit integration substitute: always requests clarification, never guesses."""

    def parse_time_range(
        self, text: str, ref_time: datetime, tz: str = "Asia/Shanghai", calendar: Any = None
    ) -> TimeRangeResult:
        if ref_time.tzinfo is None or ref_time.utcoffset() is None:
            raise ValueError("解析参照时刻必须带时区")
        return TimeRangeResult(needs_clarification=True)

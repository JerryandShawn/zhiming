"""Flat date intents; calendar authority and current time are never supplied by the model."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .parameters import Parameters


class DateCalc(Parameters):
    op: (
        Literal["diff", "add", "age", "weekday", "lunar_to_solar", "solar_to_lunar"]
        | None
    ) = None
    a: str | None = Field(
        default=None,
        max_length=80,
        description="公历 YYYY-MM-DD/带时区 ISO；农历 YYYY-闰MM-DD",
    )
    b: str | None = Field(default=None, max_length=80)
    n: int | None = Field(default=None, ge=-36600, le=36600)
    unit: Literal["day", "week", "month", "year"] | None = None
    inclusive: bool = False
    # Previously server-only calls keep their absolute-only contract.
    operation: Literal["add_days", "difference"] | None = None
    start_date: str | None = None
    end_date: str | None = None
    days: int | None = Field(default=None, ge=-36600, le=36600)

    @field_validator("start_date", "end_date")
    @classmethod
    def absolute_date(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value) != 10 or date.fromisoformat(value).isoformat() != value
        ):
            raise ValueError("日期必须为YYYY-MM-DD")
        return value

    @model_validator(mode="after")
    def operation_arguments(self) -> DateCalc:
        if self.operation is not None:
            if (
                any(
                    value is not None
                    for value in (self.op, self.a, self.b, self.n, self.unit)
                )
                or self.inclusive
            ):
                raise ValueError("两种日期参数格式不能混用")
            if self.start_date is None:
                raise ValueError("绝对日期计算需要start_date")
            if self.operation == "add_days" and (
                self.days is None or self.end_date is not None
            ):
                raise ValueError("日期加日只接受days")
            if self.operation == "difference" and (
                self.end_date is None or self.days is not None
            ):
                raise ValueError("日期差只接受end_date")
            return self
        if (
            self.op is None
            or not self.a
            or any(
                value is not None
                for value in (self.start_date, self.end_date, self.days)
            )
        ):
            raise ValueError("日期计算需要op和a，不接受旧格式字段")
        if self.op == "diff" and (not self.b or self.n is not None):
            raise ValueError("日期差需要b，不接受n")
        if self.op == "add" and (
            self.n is None or self.b is not None or self.inclusive
        ):
            raise ValueError("日期加减需要n，不接受b或inclusive")
        if self.op not in {"diff", "add"} and (
            self.n is not None or self.unit is not None or self.inclusive
        ):
            raise ValueError("此日期操作不接受n、unit或inclusive")
        if self.op not in {"diff", "age"} and self.b is not None:
            raise ValueError("此日期操作不接受b")
        if self.inclusive and self.unit not in {None, "day", "week"}:
            raise ValueError("首尾计数只适用于日或周")
        return self

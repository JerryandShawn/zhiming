"""Model-facing intent only; authority and birth values come from application state."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from mingjing_core.agent.tools.date_parameters import DateCalc as DateCalc
from mingjing_core.agent.tools.parameters import Parameters
from mingjing_core.domain.consultation import ProfileField
from mingjing_core.skills.loader import SkillLibrary

_SKILL_CATALOG = SkillLibrary().catalog["systems"]
_SKILL_TOPICS = tuple(sorted({row["topic"] for item in _SKILL_CATALOG.values() for row in item["chapters"]}))


class ChartSkill(Parameters):
    system: str = Field(json_schema_extra={"enum": list(_SKILL_CATALOG)})
    topic: str = Field(json_schema_extra={"enum": list(_SKILL_TOPICS)})

    @model_validator(mode="after")
    def allowed_chapter(self) -> ChartSkill:
        package = _SKILL_CATALOG.get(self.system)
        if package is None or self.topic not in {row["topic"] for row in package["chapters"]}:
            raise ValueError("技能体系和章节不匹配")
        return self


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

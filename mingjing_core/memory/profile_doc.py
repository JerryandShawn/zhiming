"""Eight About Me sections and strictly source-bound reflection suggestions."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, StrictInt

# Shared with the previously delivered memory2/reflection.py section contract.
SECTION_TITLES = {
    1: "称呼与基本情况",
    2: "现在的生活",
    3: "在意的事与目标",
    4: "重要的人",
    5: "偏好与禁忌",
    6: "沟通偏好",
    7: "命理档案摘要",
    8: "正在跟进",
}
COMMUNICATION = re.compile(r"回答.{0,5}(?:长|短|详细|简洁)|直说|委婉|命理术语|沟通|语气")


class ProfileSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    section: StrictInt = Field(ge=1, le=8)
    text: str = Field(min_length=1, max_length=800)
    fact_ids: list[str] = Field(min_length=1, max_length=20)
    confidence: float = Field(default=0.8, ge=0, le=1, allow_inf_nan=False)
    item_id: str | None = None


def suggested_section(fact: dict) -> int:
    """Reuse conservative section cues; model prose remains a proposal, never a fact."""
    slot, kind = fact.get("slot", ""), fact.get("requested_kind", fact.get("kind"))
    if slot in {"preferred_name", "residence_city", "employer", "job_role"} or kind == "profile":
        return 1
    if COMMUNICATION.search(fact.get("content", "")):
        return 6
    if kind in {"goal", "constraint", "concern"}:
        return 3
    if kind == "relationship" or slot == "important_people":
        return 4
    if kind in {"preference", "habit"}:
        return 5
    return 8 if kind == "event" else 2

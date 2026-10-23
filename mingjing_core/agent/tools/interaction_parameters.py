"""Second-batch case, clarification and scheduling argument contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from mingjing_core.agent.tools.parameters import Parameters


class CaseList(Parameters):
    """列出当前人物的事项索引。"""


class CaseChanges(Parameters):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    goal: str | None = Field(default=None, min_length=1, max_length=1000)
    status: Literal["open", "paused", "closed"] | None = None


class CaseUpdate(Parameters):
    id: str = Field(min_length=1, max_length=200)
    changes: CaseChanges
    expected_revision: int = Field(ge=1)
    message_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=3000)


class CaseAddEvent(Parameters):
    id: str = Field(min_length=1, max_length=200)
    kind: Literal["decided", "acted", "result", "completed", "rejected_interpretation", "progress", "feedback"]
    content: str = Field(min_length=1, max_length=3000, description="逐字来自本轮用户消息的事件内容")
    message_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)


class AskUser(Parameters):
    question: str = Field(min_length=1, max_length=500)
    options: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=4)
    allow_free_text: bool = True
    why: str = Field(min_length=1, max_length=500)
    slot: str = Field(min_length=3, max_length=10)
    changes_conclusion: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_options(self) -> AskUser:
        if len(self.options) == 1:
            raise ValueError("快捷选项应为空或包含2至4项")
        return self


class DecisionOption(Parameters):
    title: str = Field(min_length=1, max_length=120)
    benefit: str = Field(min_length=1, max_length=500)
    cost: str = Field(min_length=1, max_length=500)
    risk: str = Field(min_length=1, max_length=500)
    reversibility: str = Field(min_length=1, max_length=500)
    first_step: str = Field(min_length=1, max_length=500)


class PresentOptions(Parameters):
    options: list[DecisionOption] = Field(min_length=2, max_length=4)


class ScheduleFollowup(Parameters):
    topic: str = Field(min_length=1, max_length=300)
    due_at: str = Field(min_length=1, max_length=80, description="带时区的绝对ISO时刻")
    reason: str = Field(min_length=1, max_length=500)
    message_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=3000)
    source_fact_id: str | None = Field(default=None, max_length=200)


class SetReminder(Parameters):
    text: str = Field(min_length=1, max_length=500)
    due_at: str = Field(min_length=1, max_length=80)
    message_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=3000)

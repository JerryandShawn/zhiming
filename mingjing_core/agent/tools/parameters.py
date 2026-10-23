"""Strict model-facing arguments: runtime authority is never model-supplied."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TimeContext(Parameters):
    date: str | None = Field(default=None, description="绝对日期 YYYY-MM-DD；留空为当前时刻")
    time: str | None = Field(default=None, description="当地时间 HH:MM[:SS]；指定日期默认正午")


class CalendarLookup(Parameters):
    start_date: str = Field(description="开始日期 YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="结束日期，含当日；最多366日")


class MemorySearch(Parameters):
    query: str = Field(min_length=1, max_length=500, description="原始关键词，程序执行本地分词")
    kinds: list[Literal["fact", "message", "note", "episode"]] = Field(default=["fact"], min_length=1, max_length=4)
    limit: int = Field(default=10, ge=1, le=30)
    since: str | None = Field(default=None, description="事件或来源时间的起始日期")
    until: str | None = Field(default=None, description="事件或来源时间的结束日期")


class MemoryWrite(Parameters):
    message_id: str = Field(min_length=1, max_length=200, description="本轮受信用户消息ID")
    quote: str = Field(min_length=1, max_length=3000, description="逐字原话；不可用模型摘要代替")
    summary: str = Field(min_length=1, max_length=1000, description="仅作派生摘要，原话仍为事实依据")
    kind: Literal[
        "preference",
        "constraint",
        "background",
        "goal",
        "event",
        "concern",
        "relationship",
        "habit",
    ]
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)
    case_id: str | None = Field(default=None, max_length=200)
    sensitivity: Literal["normal", "health", "third_party", "money", "identity", "legal"] = "normal"
    date_expression: str | None = Field(default=None, max_length=200)
    event_at: str | None = Field(default=None, max_length=80)


class MemoryForget(Parameters):
    fact_id: str = Field(min_length=1, max_length=200)
    message_id: str = Field(min_length=1, max_length=200, description="明确提出撤销的本轮用户消息ID")


class NoteWrite(Parameters):
    summary: str = Field(min_length=1, max_length=2000)
    source_ids: list[str] = Field(min_length=1, max_length=20)
    inferred: Literal[True] = True


class ProfileGet(Parameters):
    """当前受信人物的已确认资料，无模型可选身份字段。"""

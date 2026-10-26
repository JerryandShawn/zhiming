"""Models choose a frozen question and spread, never cards or hidden deck data."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from mingjing_core.agent.tools.parameters import Parameters


class TarotStart(Parameters):
    question: str = Field(min_length=1, max_length=2000, description="逐字来自本轮用户消息的问题")
    message_id: str = Field(min_length=1, max_length=200)
    case_id: str | None = Field(default=None, max_length=200)
    spread_id: Literal["focus1", "reflect3", "choice5"] = "reflect3"
    draw_source: Literal["auto", "pick"] = "pick"
    reversals: bool = True
    options: dict[str, str] = Field(default_factory=dict)
    explicit_new: bool = Field(default=False, description="仅用户原话明确坚持重新抽牌时为true")


class TarotRead(Parameters):
    draw_id: str | None = Field(
        default=None, min_length=1, max_length=200, description="可省略；省略时读取本轮用户已选中并揭示的固定牌阵"
    )

"""A fixed tarot tool pair; visibility follows the persisted selected draw."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mingjing_core.agent.tools.tarot_parameters import TarotRead, TarotStart

if TYPE_CHECKING:
    from mingjing_core.agent.toolkit import ToolDefinition


def tarot_definitions() -> tuple[ToolDefinition, ...]:
    from mingjing_core.agent.toolkit import ToolDefinition

    return (
        ToolDefinition(
            "tarot_start",
            TarotStart,
            "当用户明确请求抽牌时使用。问题和选项须来自本轮原话；24小时相似问题沿用固定牌阵，"
            "重新抽牌须用户明确坚持，无痕不可写。返回固定牌阵及选牌入口；会保存牌阵，支持幂等，不代替用户揭牌。",
            False,
        ),
        ToolDefinition(
            "tarot_read",
            TarotRead,
            "当运行已选中且用户已揭示固定牌阵时使用。只接受该真实draw_id，不抽新牌、不修改牌面。"
            "返回牌面、牌义和来源；只读无副作用，来源撤销后不可读。",
        ),
    )

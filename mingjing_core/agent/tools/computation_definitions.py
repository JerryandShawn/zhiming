"""Application handlers are registered by the mainline coordinator after wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mingjing_core.agent.tools.computation_parameters import (
    ChartCompute,
    DateCalc,
    MemoryUpdate,
    ProfileUpdateRequest,
)

if TYPE_CHECKING:
    from mingjing_core.agent.toolkit import ToolDefinition


def computation_definitions() -> tuple[ToolDefinition, ...]:
    from mingjing_core.agent.toolkit import ToolDefinition

    return (
        ToolDefinition(
            "chart_compute",
            ChartCompute,
            "当回答需要实际盘面且已有确认资料时使用。只传体系、绝对目标日期和时间尺度，出生资料由程序读取；"
            "返回真实计算与来源/方法/缺口，不补未实现真太阳时能力，不修改出生资料；会存本运行可撤销的计算依据。",
        ),
        ToolDefinition(
            "date_calc",
            DateCalc,
            "当你需要算天数、间隔、年龄、星期或农历公历互换时使用，不要心算。"
            "公历输入用绝对日期或带时区ISO；农历用农历YYYY-MM-DD，闰月在月份前写闰。"
            "相对日期先按本轮此刻换算；返回结果与计算口径，只读无副作用，无写入回执。",
        ),
        ToolDefinition(
            "memory_update",
            MemoryUpdate,
            "仅当本轮用户明确纠正已有记忆时使用；需目标实际版本和逐字本轮原话。"
            "敏感更正需确认，出生资料走资料确认。返回更正或待确认回执；会写事实或确认请求，旧来源继续受撤销保护。",
            False,
        ),
        ToolDefinition(
            "profile_update_request",
            ProfileUpdateRequest,
            "当初次相识或用户要改资料时使用；fields只选需要核对的资料字段。"
            "返回待确认回执，会创建本地确认请求；真正保存须用户在确认入口操作，不能称资料已保存。",
            False,
        ),
    )

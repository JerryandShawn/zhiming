"""Fixed-order second-batch tools, independent of conversation topic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mingjing_core.agent.tools.interaction_parameters import (
    AskUser,
    CaseAddEvent,
    CaseList,
    CaseUpdate,
    PresentOptions,
    ScheduleFollowup,
    SetReminder,
)

if TYPE_CHECKING:
    from mingjing_core.agent.toolkit import ToolDefinition


def interaction_definitions() -> tuple[ToolDefinition, ...]:
    from mingjing_core.agent.toolkit import ToolDefinition

    return (
        ToolDefinition(
            "case_list",
            CaseList,
            "当需要选择或确认当前人物的事项时使用。只返回事项ID、标题、状态和版本索引，不展开其他事项原话。返回最多100项；只读无副作用。",
        ),
        ToolDefinition(
            "case_update",
            CaseUpdate,
            "当本轮用户陈述使已选事项的标题、目标或状态变化时使用。需当前用户逐字原话、已选事项和实际版本；"
            "敏感内容先确认，标题目标不能杜撰，无痕不可用。返回事项保存或待确认回执；会更新事项，支持幂等。",
            False,
        ),
        ToolDefinition(
            "case_add_event",
            CaseAddEvent,
            "当用户报告已选事项的行动、结果或进展时使用。content须逐字来自本轮用户消息，不能把模型建议当用户事件；"
            "需实际事项版本，无痕不可用。返回事件ID和版本；会保存来源绑定的反馈，支持幂等。",
            False,
        ),
        ToolDefinition(
            "ask_user",
            AskUser,
            "当缺少会改变结论的信息时使用。slot写明3至10字槽位，说明答案改变哪个结论；同轮仅一次、同槽最多两次，"
            "已拒答就带假设回答。返回提问卡并结束本轮，用户回复进入下一轮；会更新线程澄清计数，无痕仍可提问。",
            False,
            private_allowed=True,
        ),
        ToolDefinition(
            "present_options",
            PresentOptions,
            "当用户比较行动或决策选项时使用。给2至4项，分别写收益、成本、风险、可逆性和第一步；"
            "不替用户做决定或承诺结果。返回结构化决策卡；只读无副作用，不结束本轮。",
        ),
        ToolDefinition(
            "schedule_followup",
            ScheduleFollowup,
            "当用户提到未来事件且允许主动跟进时使用。需逐字本轮来源、已确认日期；歧义先问，关闭主动跟进或无痕时不可写。"
            "返回本地跟进回执；会保存due_at和来源，发送由后续服务另行授权处理，不在此工具投递。",
            False,
        ),
        ToolDefinition(
            "set_reminder",
            SetReminder,
            "仅当用户本轮明确要求提醒时使用。提醒文本须来自原话，绝对日期和当地时分须确认；缺时间先问，无痕需要单独保存确认。"
            "返回本地提醒回执；会保存due_at和来源，支持幂等，不直接发送消息。",
            False,
            private_allowed=True,
        ),
    )

"""Intent-disclosed P8 tools, with local derived evidence and no fact writes."""

from .p8_parameters import Almanac, DailyTransit, WindowSearch


def p8_definitions():
    from mingjing_core.agent.toolkit import ToolDefinition

    return (
        ToolDefinition(
            "daily_transit",
            DailyTransit,
            "明确问某日运势或流日时使用；绝对日期由此刻换算，出生资料由程序读取。"
            "返回北京时间12点快照及真实命中规则，不代表全天应期，不改变出生事实；会保存本轮可撤销依据。",
            False,
        ),
        ToolDefinition(
            "window_search",
            WindowSearch,
            "明确择日时使用；只传最多366日绝对区间、六种已列目的和分页。"
            "返回可核对的候选排序及原始正负依据，不保证成功、不替代现实日程；会保存本轮可撤销依据。",
            False,
        ),
        ToolDefinition(
            "almanac",
            Almanac,
            "明确问黄历宜忌时使用；只传绝对日期，不读取出生档案。"
            "返回通用黄历及来源，不是个人预测；会保存本轮可撤销依据，不写用户事实。",
            False,
        ),
    )

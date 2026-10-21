"""Independent T/R/Q scenarios add DB assertions, not new frozen-corpus gold."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from tools.eval.schema import Scenario, load_scenarios


def question(text: str, slot: str) -> dict[str, Any]:
    return {
        "tool_call": {
            "name": "ask_user",
            "arguments": {
                "question": text,
                "options": ["选项甲", "选项乙"],
                "allow_free_text": True,
                "why": "答案改变建议范围",
                "slot": slot,
                "changes_conclusion": "影响建议的取舍顺序",
            },
        }
    }


def scenario(identity: str, category: str, title: str, turns: list[dict], scripts: list[list[dict]]) -> dict[str, Any]:
    return {
        "id": identity,
        "title": title,
        "category": category,
        "clock": "2026-10-17T10:30:00+08:00",
        "targets": ["v4"],
        "seed": {"profile": "empty_profile", "synthetic": True},
        "turns": turns,
        "scripted": [{"turn": index, "model": actions} for index, actions in enumerate(scripts, 1)],
        "notes": "独立v4扩充契约；实际工具结果/线程/信封断言，不替换冻结47项。",
    }


def midnight_scenario() -> dict[str, Any]:
    call = {"tool_call": {"name": "time_context", "arguments": {}}}
    first = scenario(
        "T01",
        "time",
        "UTC跨午夜按owner上海时区",
        [
            {
                "user": "现在几号",
                "at": "2026-10-17T15:55:00+00:00",
                "expect": {
                    "tools_called": ["time_context"],
                    "db": [
                        {"path": "observed_tools.0.output.data.solar", "equals": "2026-10-17"},
                        {"path": "observed_tools.0.output.data.weekday", "equals": "星期六"},
                    ],
                },
            },
            {
                "user": "十分钟后呢",
                "at": "2026-10-17T16:05:00+00:00",
                "expect": {
                    "tools_called": ["time_context"],
                    "db": [
                        {"path": "observed_tools.0.output.data.solar", "equals": "2026-10-18"},
                        {"path": "observed_tools.0.output.data.weekday", "equals": "星期日"},
                    ],
                },
            },
        ],
        [[call, {"text": "现在按上海时区是10月17日。"}], [call, {"text": "已经是10月18日。"}]],
    )
    return first


def zi_hour_scenario() -> dict[str, Any]:
    second = scenario(
        "T02",
        "time",
        "指定晚子时仍使用固定历法工具",
        [
            {
                "user": "核对10月17日23点40的口径",
                "expect": {
                    "tools_called": ["time_context"],
                    "db": [
                        {"path": "observed_tools.0.output.data.ganzhi.hour", "equals": "丙子"},
                        {"path": "observed_tools.0.output.data.zi_hour_note", "contains": "晚子时不换日"},
                    ],
                },
            }
        ],
        [
            [
                {"tool_call": {"name": "time_context", "arguments": {"date": "2026-10-17", "time": "23:40"}}},
                {"text": "晚子时存在换日口径差异，已按工具确认。"},
            ]
        ],
    )
    return second


def workday_scenario() -> dict[str, Any]:
    third = scenario(
        "T08",
        "time",
        "调休与周末按实际区间结果区分",
        [
            {
                "user": "查10月10日至11日是否休息",
                "expect": {
                    "tools_called": ["calendar_lookup"],
                    "db": [
                        {"path": "observed_tools.0.output.data.days.0.day_status.kind", "equals": "adjusted_workday"},
                        {"path": "observed_tools.0.output.data.days.0.day_status.is_off", "equals": False},
                        {"path": "observed_tools.0.output.data.days.1.day_status.is_off", "equals": True},
                    ],
                },
            }
        ],
        [
            [
                {
                    "tool_call": {
                        "name": "calendar_lookup",
                        "arguments": {"start_date": "2026-10-10", "end_date": "2026-10-11"},
                    }
                },
                {"text": "10月10日调休上班，11日休息。"},
            ]
        ],
    )
    return third


def time_scenarios() -> list[dict[str, Any]]:
    return [midnight_scenario(), zi_hour_scenario(), workday_scenario()]


def own_reply_scenario() -> dict[str, Any]:
    own = scenario(
        "R02",
        "memory_recall",
        "搜索实际助手回复而非猜测方案B",
        [
            {
                "user": "第二个方案是什么",
                "expect": {
                    "tools_called": ["memory_search"],
                    "db": [
                        {"path": "observed_tools.0.output.data.items.0.role", "equals": "assistant"},
                        {"path": "observed_tools.0.output.data.items.0.content", "contains": "内部转岗"},
                    ],
                },
            }
        ],
        [
            [
                {"tool_call": {"name": "memory_search", "arguments": {"query": "内部转岗", "kinds": ["message"]}}},
                {"text": "第二个方案是内部转岗。"},
            ]
        ],
    )
    own["seed"]["thread"] = [
        {
            "id": "prior-user",
            "role": "user",
            "content": "请给三个方案",
            "at": "2026-10-17T09:00:00+08:00",
            "channel": "web",
        },
        {
            "id": "prior-assistant",
            "role": "assistant",
            "content": "A留任；B内部转岗；C外部求职。",
            "at": "2026-10-17T09:01:00+08:00",
            "channel": "web",
        },
    ]
    return own


def recall_scenarios(frozen: dict[str, Scenario]) -> list[dict[str, Any]]:
    rows = [own_reply_scenario()]
    for identity in ("R03", "R07"):
        original = frozen[identity]
        fact = original.seed.facts[0]
        item = scenario(
            identity,
            "memory_recall",
            "真实跨渠道或长历史检索的精确事实",
            [
                {
                    "user": original.turns[0].user,
                    "expect": {
                        "tools_called": ["memory_search"],
                        "db": [
                            {"path": "observed_tools.0.output.data.items.0.id", "equals": fact.id},
                            {"path": "observed_tools.0.output.data.items.0.content", "contains": fact.quote},
                        ],
                    },
                }
            ],
            [
                [
                    {"tool_call": {"name": "memory_search", "arguments": {"query": fact.quote, "kinds": ["fact"]}}},
                    {"text": "已查询实际授权来源，再继续讨论。"},
                ]
            ],
        )
        item["seed"] = deepcopy(original.seed.model_dump(mode="json"))
        rows.append(item)
    return rows


def question_scenarios() -> list[dict[str, Any]]:
    ask = question("你更看重成长还是稳定？", "工作取舍偏好")
    first = scenario(
        "Q01",
        "question",
        "真实ask_user结束本轮且事件匹配信封",
        [
            {
                "user": "你好",
                "expect": {
                    "tools_called": ["ask_user"],
                    "events": ["ask_user", "final"],
                    "max_questions": 1,
                    "db": [{"path": "run_result.asked.question", "equals": "你希望我怎么称呼你？"}],
                },
            }
        ],
        [[question("你希望我怎么称呼你？", "用户称呼")]],
    )
    second = scenario(
        "Q03",
        "question",
        "下一轮回答自动填充澄清槽而不写事实",
        [
            {"user": "我该怎么选岗位", "expect": {"events": ["ask_user", "final"]}},
            {
                "user": "我更看重成长空间",
                "expect": {
                    "max_questions": 0,
                    "tools_not_called": ["ask_user"],
                    "db": [
                        {"kind": "thread", "where": {"data.clarify_slots.0.status": "filled"}, "count": 1},
                        {"kind": "fact", "count": 0},
                    ],
                },
            },
        ],
        [[ask], [{"text": "按成长空间来比较项目和导师。"}]],
    )
    third = scenario(
        "Q06",
        "question",
        "明确拒答后同槽不可再问",
        [
            {"user": "帮我比较岗位", "expect": {"events": ["ask_user", "final"]}},
            {
                "user": "先别问了",
                "expect": {
                    "max_questions": 0,
                    "db": [
                        {"kind": "thread", "where": {"data.clarify_slots.0.status": "declined"}, "count": 1},
                        {"path": "observed_tools.0.output.data.error", "equals": "slot_declined"},
                    ],
                },
            },
        ],
        [[ask], [ask, {"text": "好，先按已有信息给一个保守框架。"}]],
    )
    return [first, second, third]


def write_extensions(destination: Path) -> None:
    from .v4_gateway_extensions import gateway_scenarios
    from .v4_safety_extensions import safety_scenarios

    frozen = {case.id: case for case in load_scenarios(destination.parent / "scenarios")}
    destination.mkdir(parents=True, exist_ok=True)
    data_rows = time_scenarios() + recall_scenarios(frozen) + question_scenarios()
    data_rows += safety_scenarios(scenario) + gateway_scenarios(scenario)
    for data in data_rows:
        valid = Scenario.model_validate(data)
        path = destination / (valid.id + ".yaml")
        path.write_text(
            yaml.safe_dump(valid.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


if __name__ == "__main__":
    write_extensions(Path(__file__).resolve().parents[1] / "scenarios_v4_extensions")

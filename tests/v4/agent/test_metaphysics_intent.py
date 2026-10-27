"""42 section 2.4 disclosure priority; intent never constitutes consent."""

from dataclasses import fields
from types import SimpleNamespace

import pytest

from mingjing_core.agent.tool_visibility import (
    CONDITIONAL_TOOLS,
    RESIDENT_TOOLS,
    VisibilityState,
    select_visible,
)
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.application.metaphysics_intent import daily_offsets, metaphysics_intent


@pytest.mark.parametrize(
    "text,expected",
    [
        ("我和她的星盘合不合", "synastry"),
        ("请做合盘", "synastry"),
        ("哪几天适合签约", "window"),
        ("什么时候适合面试", "window"),
        ("帮我挑个日子", "window"),
        ("今天黄历宜忌是什么", "almanac"),
        ("明天运势如何", "daily"),
        ("2026-10-28流日", "none"),
        ("10月28日运势", "none"),
        ("今天顺不顺", "daily"),
        ("今天运势和黄历", "almanac"),
        ("今天黄历，哪天适合搬家？也想合盘", "synastry"),
        ("别算日子", "none"),
        ("不要合盘", "none"),
        ("不用查黄历", "none"),
        ("不要明天运势", "none"),
        ("不要合盘，但是明天运势如何", "daily"),
        ("他说“请合盘”，我想聊工作", "none"),
        ("‘择日’只是引用", "none"),
        ("我想知道今天吃什么", "none"),
        ("哪天适合旅游", "none"),
        ("我想聊聊", "none"),
    ],
)
def test_single_affirmative_intent(text: str, expected: str) -> None:
    assert metaphysics_intent(text) == expected


def test_morning_report_flag_cannot_open_a_tool_without_explicit_user_intent() -> None:
    assert metaphysics_intent("", morning_report=True) == "none"
    assert metaphysics_intent("合盘", morning_report=True) == "synastry"
    assert metaphysics_intent("明天运势", morning_report=True) == "daily"


@pytest.mark.parametrize(
    "text,offsets",
    [
        ("今天运势", {0}),
        ("明天流日", {1}),
        ("今天和明天运势", {0, 1}),
        ("不要今天运势", set()),
        ("引用‘明天运势’", set()),
        ("2026-10-28流日", set()),
    ],
)
def test_daily_dates_come_only_from_explicit_affirmative_relative_words(text, offsets):
    assert daily_offsets(text) == offsets


def test_r34_all_true_state_respects_approved_capacity_and_unique_intent() -> None:
    state = VisibilityState(
        **{
            field.name: ("synastry" if field.name == "metaphysics_intent" else True)
            for field in fields(VisibilityState)
        }
    )
    definitions = [
        SimpleNamespace(name=name, read_only=True, private_allowed=False)
        for name in (*RESIDENT_TOOLS, *CONDITIONAL_TOOLS)
    ]
    context = ToolContext("synthetic", "run", "self", 0, 1, "token", "model", "a" * 64, "life:self")
    trimmed = []
    selected = select_visible(definitions, context, state, trimmed_out=trimmed)
    assert len(selected) == 15 and "synastry" in {tool.name for tool in selected}
    assert "set_reminder" in trimmed

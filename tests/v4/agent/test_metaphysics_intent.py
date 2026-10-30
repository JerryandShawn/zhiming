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


@pytest.mark.parametrize(
    "text",
    [
        "请比较2026-10-21到10-27哪天面试可作参考，把加分和减分依据都说清楚。",
        "比较2026-11-01到11-07搬家，若同分怎么办？有没有把全天时辰都扫过？",
        "帮我在2026-10-21到2027-01-21之间找签约日，一次全部算完。",
        "比较10月21日至10月27日哪天出行更合适",
    ],
)
def test_explicit_date_range_with_purpose_or_which_day_opens_window(text):
    assert metaphysics_intent(text) == "window"


@pytest.mark.parametrize(
    "text",
    [
        "比较这两份工作哪个更适合我",
        "今天适合面试吗",
        "2026-10-21到10-27我要出差",
        "比较2026-10-21到10-27的天气",
        "不要择日，只比较2026-10-21到10-27的行程",
    ],
)
def test_ranges_or_comparisons_without_the_window_shape_do_not_open_window(text):
    assert metaphysics_intent(text) != "window"


def test_window_range_keeps_priority_below_synastry_and_above_almanac_and_daily():
    assert metaphysics_intent("请合盘并比较2026-10-21到10-27哪天面试") == "synastry"
    assert metaphysics_intent("比较2026-10-21到10-27哪天面试，顺便看黄历") == "window"
    assert metaphysics_intent("比较2026-10-21到10-27哪天面试，今天运势如何") == "window"


def test_explicit_comparison_of_my_relationship_structure_with_a_named_person_opens_synastry():
    assert metaphysics_intent("我已在确认卡点了本次同意，请比较我和小禾的关系结构，只做这一次。") == "synastry"


@pytest.mark.parametrize("text", ["我和同事的关系怎么处理", "比较我和小禾的工资", "我和小禾的关系结构很复杂", "不要比较我和小禾的关系结构"])
def test_plain_relationship_talk_or_negation_does_not_open_synastry(text):
    assert metaphysics_intent(text) != "synastry"

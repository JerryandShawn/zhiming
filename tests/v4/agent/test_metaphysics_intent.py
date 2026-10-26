"""42 section 2.4 disclosure priority; intent never constitutes consent."""

from dataclasses import fields
from types import SimpleNamespace

import pytest

from mingjing_core.agent.tool_visibility import (
    CONDITIONAL_TOOLS,
    RESIDENT_TOOLS,
    ToolVisibilityConflict,
    VisibilityState,
    select_visible,
)
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.application.metaphysics_intent import metaphysics_intent


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
        ("2026-10-28流日", "daily"),
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


def test_native_morning_report_fallback_does_not_override_explicit_priority() -> None:
    assert metaphysics_intent("", morning_report=True) == "daily"
    assert metaphysics_intent("合盘", morning_report=True) == "synastry"


def test_pre_p8_all_true_state_exposes_existing_resident_capacity_conflict() -> None:
    # Baseline before registering any P8 tools. This assertion must be replaced
    # with the approved <=15 disclosure contract when residents are demoted.
    state = VisibilityState(**{field.name: True for field in fields(VisibilityState)})
    definitions = [
        SimpleNamespace(name=name, read_only=True, private_allowed=False)
        for name in (*RESIDENT_TOOLS, *CONDITIONAL_TOOLS)
    ]
    context = ToolContext("synthetic", "run", "self", 0, 1, "token", "model", "a" * 64, "life:self")
    with pytest.raises(ToolVisibilityConflict):
        select_visible(definitions, context, state)

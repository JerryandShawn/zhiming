"""Board 42 demotes two tools; native source and original safety gates still apply."""

from dataclasses import fields, replace

import pytest

from mingjing_core.agent.tool_visibility import ToolVisibilityConflict, VisibilityState
from mingjing_core.application.agent_tool_visibility import reminder_requested

from .test_tool_visibility import names
from .test_tool_visibility_pg import model_context
from .test_toolkit_pg import setup


@pytest.mark.parametrize(
    "text,expected",
    [
        ("明天八点提醒我带伞", True),
        ("给我设一个闹钟", True),
        ("请到点通知我", True),
        ("不要提醒我", False),
        ("他说“明天提醒我”，我只是转述", False),
        ("文章写着‘设一个闹钟’，先讨论文章", False),
        ("不要提醒今天的事，但是明天提醒我出门", False),
        ("别忘了提醒我开会", True),
        ("Remind me to call", True),
        ("Don't remind me to call", False),
        ("假设我说提醒我开会", False),
        ("我想谈工作", False),
    ],
)
def test_reminder_disclosure_uses_unquoted_affirmative_request(text, expected):
    assert reminder_requested(text) is expected


@pytest.mark.parametrize(
    "text,calendar,reminder",
    [
        ("普通合成对话", False, False),
        ("查一下日历中的假日调休", True, False),
        ("明天八点提醒我带伞", True, True),
        ("不要提醒我，只谈工作", False, False),
        ("他说“给我设一个闹钟”，我没有这个请求", False, False),
    ],
)
def test_native_pg_source_controls_calendar_and_reminder_disclosure(p2_repo, text, calendar, reminder):
    h = setup(p2_repo, text)
    ctx = model_context(h.run)
    tools = {tool.name for tool in h.registry.specs(ctx)}
    assert ("calendar_lookup" in tools, "set_reminder" in tools) == (calendar, reminder)
    assert len(tools) <= 15
    assert "set_reminder" not in {tool.name for tool in h.registry.specs(replace(ctx, crisis=True))}
    assert ("set_reminder" in {tool.name for tool in h.registry.specs(replace(ctx, incognito=True))}) is reminder
    h.finish()


def test_conditional_required_cannot_fabricate_a_reminder_request_and_cap_is_not_relaxed():
    assert "set_reminder" not in names(VisibilityState(), required=("set_reminder",))
    assert "set_reminder" in names(VisibilityState(reminder_requested=True))
    flags = {field.name: True for field in fields(VisibilityState) if field.type in (bool, "bool")}
    with pytest.raises(ToolVisibilityConflict):
        names(VisibilityState(**flags, metaphysics_intent="synastry"))

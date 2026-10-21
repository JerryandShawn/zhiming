"""Intent rules inspect the whole real source, including negation outside quotes."""

from __future__ import annotations

import pytest

from mingjing_core.application.agent_tools_followups import reminder_intent


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-10-21 09:00不要提醒我开会", "declined"),
        ("2026-10-21 09:00别提醒我开会", "declined"),
        ("2026-10-21开会无需通知我", "declined"),
        ("2026-10-21开会不需要闹钟", "declined"),
        ("取消明天的提醒", "declined"),
        ("停止通知我", "declined"),
        ("Don't remind me to call", "declined"),
        ("Do not set an alarm", "declined"),
        ("提醒我开会，但又不要提醒我", "ambiguous"),
        ("假设我说提醒我开会", "ambiguous"),
        ("同事说：提醒我开会", "ambiguous"),
        ("他说“提醒我开会”", "ambiguous"),
        ("翻译这句话：remind me", "ambiguous"),
        ("别忘了提醒我开会", "confirmed"),
        ("千万别忘记提醒我开会", "confirmed"),
        ("请在2026-10-21通知我开会", "confirmed"),
        ("给我设个开会闹钟", "confirmed"),
        ("请提醒我开会", "confirmed"),
        ("Remind me to call", "confirmed"),
        ("Set an alarm", "confirmed"),
        ("我周三有会议", "absent"),
        ("谢谢", "absent"),
    ],
)
def test_reminder_intent_preserves_positive_negative_and_ambiguous_sources(text: str, expected: str) -> None:
    assert reminder_intent(text) == expected


def test_selected_quote_cannot_remove_outer_negation() -> None:
    text = "不要提醒我开会"
    assert reminder_intent(text, 2, len(text)) == "declined"

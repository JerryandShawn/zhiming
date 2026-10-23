"""Opt-in composition preserves the original message and never drops intervening business text."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timeparse.extended_v2 import absolutize_extended, parse_time_range_extended

REF = datetime(2026, 10, 17, 2, tzinfo=UTC)


@pytest.mark.parametrize("text", ["明天面试", "tomorrow interview", "tomorrow下午三点面试"])
def test_one_confirmed_expression_preserves_non_time_prefix_suffix_and_original(text):
    result = absolutize_extended(text, REF)
    assert result.replaced and result.original_text == text
    lower, upper = result.result.span
    assert result.text == text[:lower] + result.result.normalized_text + text[upper:]
    assert "2026-10-18" in result.text
    assert result.result.start.astimezone(ZoneInfo("Asia/Shanghai")).day == 18


@pytest.mark.parametrize(
    "text",
    [
        "tomorrow或者后天面试",
        "明天 interview，next Friday dinner",
        "tomorrow meeting at 3pm",
        "my birthday tomorrow",
        "我生日，下周三再谈",
    ],
)
def test_independent_or_unresolved_profile_dates_cannot_be_silently_rewritten(text):
    result = absolutize_extended(text, REF)
    assert result.result.needs_clarification and not result.replaced
    assert result.text == result.original_text == text


@pytest.mark.parametrize("text", ["I have 3pm-style notes", "a tomorrowland poster", "普通整理备忘"])
def test_non_time_words_never_turn_into_dates(text):
    result = absolutize_extended(text, REF)
    assert not result.replaced and not result.result.needs_clarification
    assert result.result.start is None and result.result.confidence == 0


def test_oversize_input_is_rejected_before_any_profile_lookup():
    class ForbiddenProfiles:
        def lookup(self, scope, key):
            raise AssertionError("超长输入不得查资料")

    text = "my birthday " + "x" * 100_000
    result = parse_time_range_extended(text, REF, profiles=ForbiddenProfiles())
    assert result.needs_clarification and result.reason == "input_too_long"
    assert result.original_text == text


@pytest.mark.parametrize("text", ["明天小王下午三点面试", "明天提醒我下午三点面试", "下午三点小王明天面试"])
def test_chinese_time_span_cannot_swallow_person_or_reminder_words(text):
    result = absolutize_extended(text, REF)
    assert result.result.needs_clarification
    assert result.text == text and not result.replaced


@pytest.mark.parametrize("text", ["every year anniversary", "每年生日"])
def test_known_cycle_stays_a_cycle_even_when_profile_date_is_missing(text):
    result = absolutize_extended(text, REF)
    assert result.result.needs_clarification and result.result.kind == "recurring"
    assert result.result.recurrence is None and result.result.start is None
    assert not result.replaced and result.text == text

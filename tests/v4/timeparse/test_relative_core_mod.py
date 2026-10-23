"""Public-contract edges beyond the independent acceptance table: composition, DST and provenance."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timeparse import absolutize, parse_time_range
from mingjing_core.timeparse.numerals import parse_number

ZONE = ZoneInfo("Asia/Shanghai")
REF = datetime(2026, 10, 17, 12, tzinfo=ZONE)


def test_combined_date_clock_is_one_absolute_event_and_absolutization_is_idempotent() -> None:
    ref = datetime(2026, 10, 20, 12, tzinfo=ZONE)
    original = "请把下周三下午三点面试记下来。"
    converted = absolutize(original, ref)
    assert converted.replaced and converted.original_text == original
    assert converted.text == "请把2026-10-28（周三）15:00面试记下来。"
    assert absolutize(converted.text, ref).text == converted.text
    assert converted.result.start == datetime(2026, 10, 28, 7, tzinfo=UTC)
    assert converted.result.start == converted.result.end


@pytest.mark.parametrize(
    "text",
    [
        "今天开会，明天面试",
        "今天开会明天面试",
        "下周三开会，明天下午三点面试",
        "今天开会；下午三点面试",
        "明天或者后天面试",
        "明天和后天面试",
    ],
)
def test_multiple_distinct_events_or_alternatives_are_not_silently_bound(text: str) -> None:
    result = parse_time_range(text, REF)
    assert result.needs_clarification and len(result.candidates) >= 2
    assert not absolutize(text, REF).replaced


def test_yearless_past_month_day_exposes_both_years_and_preserves_original() -> None:
    ref = datetime(2026, 12, 31, 10, tzinfo=ZONE)
    result = parse_time_range("1月1日面试", ref)
    assert result.needs_clarification
    assert {candidate.start.astimezone(ZONE).year for candidate in result.candidates} == {2026, 2027}
    assert absolutize("1月1日面试", ref).text == "1月1日面试"


@pytest.mark.parametrize(
    "text", ["每周三", "每周三下午三点", "每天上午八点", "每月31日", "每年2月29日", "每月初一", "每年农历八月十五"]
)
def test_recurring_input_cannot_be_rewritten_as_a_one_off_fact(text: str) -> None:
    result = parse_time_range(text, REF)
    assert result.kind == "recurring" and result.recurrence
    assert absolutize(text, REF).text == text and not absolutize(text, REF).replaced


@pytest.mark.parametrize("text", ["上午14点", "凌晨15点", "明天25点", "2026-02-30", "本周八", "下周九"])
def test_invalid_time_is_not_promoted_from_a_partial_match(text: str) -> None:
    result = parse_time_range(text, REF)
    assert result.start is None or result.needs_clarification
    assert not absolutize(text, REF).replaced


def test_evening_twelve_is_next_midnight_not_noon() -> None:
    result = parse_time_range("明天晚上十二点", REF)
    assert result.start == datetime(2026, 10, 19, tzinfo=ZONE)


@pytest.mark.parametrize(
    "ref",
    [
        datetime(2026, 3, 8, 1, 30, tzinfo=ZoneInfo("America/New_York")),
        datetime(2026, 11, 1, 0, 30, tzinfo=ZoneInfo("America/New_York")),
    ],
)
def test_hour_duration_uses_elapsed_utc_through_dst(ref: datetime) -> None:
    result = parse_time_range("两小时后", ref, "America/New_York")
    assert result.start - ref.astimezone(UTC) == timedelta(hours=2)
    assert result.start == result.end


@pytest.mark.parametrize(
    "day,time_text,reason",
    [
        (datetime(2026, 3, 8, 0, tzinfo=ZoneInfo("America/New_York")), "今天02:30", "nonexistent_wall_clock"),
        (datetime(2026, 11, 1, 0, tzinfo=ZoneInfo("America/New_York")), "今天01:30", "ambiguous_wall_clock"),
    ],
)
def test_nonexistent_and_repeated_wall_time_require_clarification(day: datetime, time_text: str, reason: str) -> None:
    result = parse_time_range(time_text, day, "America/New_York")
    assert result.needs_clarification and result.reason == reason
    assert len({candidate.start for candidate in result.candidates}) == 2


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("零", 0),
        ("两", 2),
        ("十三", 13),
        ("二十三", 23),
        ("廿三", 23),
        ("一百零二", 102),
        ("2026", 2026),
        ("二〇二六", 2026),
    ],
)
def test_number_grammar_has_independent_known_values(raw: str, expected: int) -> None:
    assert parse_number(raw) == expected


def test_result_dict_is_json_safe_and_repr_excludes_private_source_text() -> None:
    result = parse_time_range("明天处理合成的私人事项", REF)
    serialized = result.as_dict()
    assert serialized["start"].endswith("+00:00")
    assert serialized["original_text"] == "明天处理合成的私人事项"
    assert "私人事项" not in repr(result)


def test_naive_reference_is_a_caller_error_and_host_timezone_is_never_guessed() -> None:
    with pytest.raises(ValueError, match="带时区"):
        parse_time_range("明天", datetime(2026, 10, 17, 12))

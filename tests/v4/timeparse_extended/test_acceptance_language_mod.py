"""Independent pre-implementation English/mixed-date truth; no parser-derived labels."""

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timeparse.extended_v2 import absolutize_extended, parse_time_range_extended

MATRIX = json.loads((Path(__file__).parent / "fixtures/acceptance_expected_mod.json").read_bytes())
LANGUAGE = [row for row in MATRIX["cases"] if not row["category"].startswith("profile_")]
CLEAR = [row for row in LANGUAGE if row["category"].startswith("clear_")]
ZONES = ("Asia/Shanghai", "Asia/Tokyo", "UTC", "America/New_York", "Europe/Berlin", "Australia/Sydney")


def check_span(result, text):
    assert result.original_text == text
    assert result.span is not None and 0 <= result.span[0] < result.span[1] <= len(text)
    assert text[slice(*result.span)] == result.matched_text


@pytest.mark.parametrize("case", LANGUAGE, ids=lambda row: row["id"])
def test_frozen_english_mixed_language_and_non_time_matrix(case):
    text, ref, zone = case["text"], datetime.fromisoformat(case["ref"]), ZoneInfo(case["tz"])
    result = parse_time_range_extended(text, ref, case["tz"])
    assert result.original_text == text
    if case["category"] == "negative":
        assert result.start is None and result.end is None and not result.candidates
        assert result.confidence == 0 and not result.needs_clarification
    elif case["category"] == "clarify":
        assert result.needs_clarification
    elif case["category"] == "clear_day":
        expected = date.fromisoformat(case["date"])
        assert not result.needs_clarification and result.kind == "point" and result.granularity == "day"
        assert result.start == datetime.combine(expected, time(), zone).astimezone(UTC)
        assert result.end == datetime.combine(expected + timedelta(days=1), time(), zone).astimezone(UTC)
        assert expected.isoformat() in result.normalized_text
        check_span(result, text)
    else:
        expected = datetime.fromisoformat(case["instant"]).astimezone(UTC)
        assert not result.needs_clarification and result.kind == "point"
        assert result.start == result.end == expected
        check_span(result, text)
    if case["category"] in {"negative", "clarify"}:
        absolute = absolutize_extended(text, ref, case["tz"])
        assert absolute.original_text == absolute.text == text and not absolute.replaced


@pytest.mark.parametrize("case", CLEAR, ids=lambda row: row["id"])
def test_only_confirmed_original_span_is_absolutized_without_rewriting_surroundings(case):
    text = "记录：「" + case["text"] + "」；原话保留用于复核。"
    ref = datetime.fromisoformat(case["ref"])
    absolute = absolutize_extended(text, ref, case["tz"])
    result = absolute.result
    assert absolute.original_text == text and not result.needs_clarification
    check_span(result, text)
    lower, upper = result.span
    assert absolute.text == text[:lower] + result.normalized_text + text[upper:]
    assert absolute.text.startswith("记录：「") and absolute.text.endswith("」；原话保留用于复核。")
    assert (case.get("date") or case["instant"][:10]) in absolute.text
    assert absolute.replaced


@pytest.mark.parametrize("text", ["tomorrow meeting at 3pm", "tomorrow 与小李复盘 at 3pm", "明天开会 at 3pm"])
def test_a_single_replacement_span_cannot_swallow_meaningful_event_text_between_date_and_clock(text):
    result = absolutize_extended(text, datetime.fromisoformat("2026-10-17T12:00:00+08:00"))
    assert result.original_text == result.text == text and not result.replaced
    assert result.result.needs_clarification


@pytest.mark.parametrize(
    ("text", "ref", "expected"),
    [
        ("04/05/2026", "2026-10-17T12:00:00+08:00", {"2026-04-05", "2026-05-04"}),
        ("Saturday", "2026-10-17T12:00:00+08:00", {"2026-10-17", "2026-10-24"}),
        ("next Friday", "2026-10-19T12:00:00+08:00", {"2026-10-23", "2026-10-30"}),
    ],
)
def test_ambiguity_contains_distinct_meaningful_dates_instead_of_a_certain_guess(text, ref, expected):
    result = parse_time_range_extended(text, datetime.fromisoformat(ref))
    candidates = {
        item.start.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
        for item in result.candidates
        if item.start is not None
    }
    assert result.needs_clarification and expected <= candidates


@pytest.mark.parametrize("seed", range(40))
def test_1000_random_reference_dates_and_zones_are_independent_of_reference_representation(seed):
    rng = Random(583201 + seed)
    for _ in range(25):
        local = date(2005, 1, 1) + timedelta(days=rng.randrange(0, 365 * 25))
        zone = ZoneInfo(rng.choice(ZONES))
        ref = datetime.combine(local, time(rng.randrange(24), rng.randrange(60)), zone)
        expected = local + timedelta(days=1)
        result = parse_time_range_extended("tomorrow", ref, zone.key)
        mirrored = parse_time_range_extended("tomorrow", ref.astimezone(ZoneInfo(rng.choice(ZONES))), zone.key)
        assert not result.needs_clarification and result.start is not None and result.end is not None
        assert result.start == datetime.combine(expected, time(), zone).astimezone(UTC)
        assert result.end == datetime.combine(expected + timedelta(days=1), time(), zone).astimezone(UTC)
        assert result.start == mirrored.start and result.end == mirrored.end
        assert result.start.utcoffset() == result.end.utcoffset() == timedelta(0)


@pytest.mark.parametrize("text", ["tomorrow", "my birthday", "October 28, 2026"])
def test_naive_reference_cannot_silently_borrow_the_host_timezone(text):
    with pytest.raises(ValueError):
        parse_time_range_extended(text, datetime(2026, 10, 17, 12))

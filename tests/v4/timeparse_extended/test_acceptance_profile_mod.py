"""Independent scoped provenance and explicit birthday-observance policy acceptance."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timeparse.extended_v2 import absolutize_extended, parse_time_range_extended
from mingjing_core.timeparse.profile_contracts_v2 import ProfileDateRecord, ProfileScope
from mingjing_core.timeparse.profile_dates_v2 import parse_profile_date

MATRIX = json.loads((Path(__file__).parent / "fixtures/acceptance_expected_mod.json").read_bytes())
CASES = [row for row in MATRIX["cases"] if row["category"].startswith("profile_")]
SCOPE = ProfileScope("owner", "self")
BASE = datetime(2026, 10, 17, 12, tzinfo=ZoneInfo("Asia/Shanghai"))


class UnfilteredProfilePort:
    """Hostile projection intentionally does not provide implicit source/owner filtering."""

    def __init__(self, records):
        self.records = tuple(records)
        self.calls = []

    def lookup(self, scope, key):
        self.calls.append((scope, key))
        return self.records


def scoped_port(case):
    record = ProfileDateRecord(
        scope=SCOPE, key=case["key"], source_id="synthetic-profile-source", confirmed=True, **case["profile"]
    )
    guard = case.get("guard")
    changes = {
        "wrong_owner": {"scope": ProfileScope("other-owner", "self")},
        "wrong_subject": {"scope": ProfileScope("owner", "other-subject")},
        "inactive": {"active": False},
        "revoked": {"revoked": True},
        "unconfirmed": {"confirmed": False},
        "not_current": {"current": False},
        "incognito": {"incognito": True},
        "revision_changed": {"current_revision": 2},
    }
    record = replace(record, **changes.get(guard, {}))
    records = [record]
    if guard == "empty":
        records = []
    if guard == "conflicting_records":
        records.append(replace(record, month=11, day=4, source_id="synthetic-second-source"))
    return None if guard == "missing_port" else UnfilteredProfilePort(records)


@pytest.mark.parametrize("case", CASES, ids=lambda row: row["id"])
def test_frozen_profile_dates_require_scope_current_source_and_explicit_missing_policy(case):
    port = scoped_port(case)
    text, ref = case["text"], datetime.fromisoformat(case["ref"])
    result = parse_time_range_extended(text, ref, case["tz"], profile_scope=SCOPE, profiles=port)
    assert result.original_text == text
    absolute = absolutize_extended(text, ref, case["tz"], profile_scope=SCOPE, profiles=port)
    assert absolute.original_text == text
    if case["category"] == "profile_clear":
        day, zone = date.fromisoformat(case["date"]), ZoneInfo(case["tz"])
        assert not result.needs_clarification and result.kind == "point"
        assert result.start == datetime.combine(day, time(), zone).astimezone(UTC)
        assert result.end == datetime.combine(day + timedelta(days=1), time(), zone).astimezone(UTC)
        assert day.isoformat() in absolute.text and absolute.replaced
    else:
        assert result.needs_clarification
        assert not absolute.replaced and absolute.text == text
        if case["category"] == "profile_guard":
            assert result.start is None and result.end is None and not result.candidates
            assert "12-03" not in result.normalized_text and "2026-12-03" not in repr(result.as_dict())


@pytest.mark.parametrize(
    "case", [row for row in CASES if row["category"] == "profile_clear"], ids=lambda row: row["id"]
)
def test_confirmed_profile_date_absolutization_only_changes_the_matching_original_span(case):
    text = "周记：「" + case["text"] + "」；其余不变。"
    absolute = absolutize_extended(
        text, datetime.fromisoformat(case["ref"]), case["tz"], profile_scope=SCOPE, profiles=scoped_port(case)
    )
    result = absolute.result
    assert absolute.original_text == text and result.original_text == text
    assert absolute.replaced and not result.needs_clarification
    assert result.span is not None and text[slice(*result.span)] == result.matched_text
    lower, upper = result.span
    assert absolute.text == text[:lower] + result.normalized_text + text[upper:]
    assert absolute.text.startswith("周记：「") and absolute.text.endswith("」；其余不变。")


@pytest.mark.parametrize("missing", ["scope", "port", "both"])
def test_missing_profile_context_never_calls_an_unscoped_lookup(missing):
    class FailOnLookup:
        def lookup(self, scope, key):
            raise AssertionError("unscoped profile lookup is forbidden")

    result = parse_profile_date(
        "我的生日",
        BASE,
        scope=None if missing in {"scope", "both"} else SCOPE,
        profiles=None if missing in {"port", "both"} else FailOnLookup(),
    )
    assert result.needs_clarification and result.start is None and not result.candidates


def test_other_profile_keys_returned_by_a_port_are_not_birthday_evidence():
    unrelated = ProfileDateRecord(SCOPE, "wedding_anniversary", 12, 3, "synthetic-profile-source", confirmed=True)
    result = parse_profile_date("我的生日", BASE, scope=SCOPE, profiles=UnfilteredProfilePort([unrelated]))
    assert result.needs_clarification and result.start is None and not result.candidates


def test_a_record_without_explicit_confirmation_cannot_be_used_as_a_birthday_fact():
    unconfirmed = ProfileDateRecord(SCOPE, "birthday", 12, 3, "synthetic-profile-source")
    result = parse_profile_date("我的生日", BASE, scope=SCOPE, profiles=UnfilteredProfilePort([unconfirmed]))
    assert result.needs_clarification and result.start is None and not result.candidates


@pytest.mark.parametrize("text", ["我妈妈的生日", "同事的生日", "his birthday", "her birthday"])
def test_someone_elses_birthday_cannot_silently_use_the_current_self_profile(text):
    birthday = ProfileDateRecord(SCOPE, "birthday", 12, 3, "synthetic-profile-source", confirmed=True)
    port = UnfilteredProfilePort([birthday])
    absolute = absolutize_extended(text, BASE, profile_scope=SCOPE, profiles=port)
    assert absolute.original_text == absolute.text == text and not absolute.replaced
    assert absolute.result.start is None and not absolute.result.candidates


def test_leap_day_observance_proposes_both_dates_instead_of_silently_choosing_a_policy():
    birthday = ProfileDateRecord(SCOPE, "birthday", 2, 29, "synthetic-profile-source", confirmed=True)
    result = parse_profile_date("今年生日", BASE, scope=SCOPE, profiles=UnfilteredProfilePort([birthday]))
    zone = ZoneInfo("Asia/Shanghai")
    dates = {item.start.astimezone(zone).date().isoformat() for item in result.candidates if item.start is not None}
    assert result.needs_clarification and {"2026-02-28", "2026-03-01"} <= dates


def test_unrelated_ordinary_english_never_looks_up_profile_data():
    class FailOnLookup:
        def lookup(self, scope, key):
            raise AssertionError("ordinary English must not access profile dates")

    assert parse_profile_date("tomorrow at 3pm", BASE, scope=SCOPE, profiles=FailOnLookup()) is None

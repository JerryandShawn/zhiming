"""Public ingestion and conflict boundaries, selected from untested behavior rather than copied conditionals."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any

import pytest

from mingjing_core.application.briefing_v2 import calendar_snapshot
from mingjing_core.application.reports_v2 import DailyTransitInput, ReportError, period_for
from mingjing_core.timekit.clock import FrozenClock

from .calendar_acceptance_support_mod import (
    DAY,
    NOW,
    SCOPE,
    p8_payload,
    p8_scope,
    p8_state,
    record,
    rendered,
    report,
    symbolic,
    wording,
)


def test_repeated_identical_record_is_displayed_once_but_changed_identity_is_rejected() -> None:
    row = record()
    result = report(records=(row, row))
    assert result.used_record_ids == (row.id,)
    assert rendered(result).count(row.text) == 1
    with pytest.raises(ReportError):
        report(records=(row, replace(row, text=wording("fact_two"))))


def test_same_document_alias_cannot_be_rebound_to_a_second_valid_source() -> None:
    one, two = record(), record(2)
    ref = replace(two.basis[0], document_id=one.basis[0].document_id)
    two = replace(two, basis=(ref,))
    with pytest.raises(ReportError) as caught:
        report(records=(one, two))
    assert one.text not in str(caught.value) and two.text not in str(caught.value)


def test_same_day_p8_duplicates_are_idempotent_and_changed_full_document_is_refused() -> None:
    payload = p8_payload()
    transit = DailyTransitInput(DAY, payload, p8_state(payload))
    result = report(scope=p8_scope(payload), transits=(transit, transit), profile_revision=1)
    assert result.coverage.rendered_snapshot_days == (DAY,)
    changed = p8_payload()
    changed["limits"].append(changed["limits"][0])
    with pytest.raises(ReportError):
        report(
            scope=p8_scope(payload),
            transits=(transit, DailyTransitInput(DAY, changed, p8_state(payload))),
            profile_revision=1,
        )


def test_synthetic_duplicates_and_outside_period_do_not_inflate_coverage() -> None:
    row = symbolic()
    result = report(synthetic_symbolic=(row, row, replace(row, id="synthetic-outside", day=date(2026, 9, 1))))
    assert result.coverage.synthetic_days == (DAY,)
    assert rendered(result).count(row.text) == 1
    with pytest.raises(ReportError):
        report(synthetic_symbolic=(row, replace(row, text=wording("fact_two"))))


@pytest.mark.parametrize("seconds", (-1, 901))
def test_future_or_stale_calendar_is_omitted_without_losing_valid_records(seconds: int) -> None:
    snapshot = calendar_snapshot(scope=SCOPE, clock=FrozenClock(NOW - timedelta(seconds=seconds)))
    row = record()
    result = report(calendar=snapshot, records=(row,))
    assert row.id in result.used_record_ids
    assert not any(section.id == "now_calendar" for section in result.sections)


def test_calendar_timezone_mismatch_degrades_instead_of_relabeling_owner_time() -> None:
    snapshot = calendar_snapshot(scope=SCOPE, clock=FrozenClock(NOW), timezone="America/New_York")
    result = report(calendar=snapshot, records=(record(),))
    assert not any(section.id == "now_calendar" for section in result.sections)
    assert result.used_record_ids == (record().id,)


@pytest.mark.parametrize("key", ("records", "transits", "synthetic_symbolic"))
@pytest.mark.parametrize("bad", ("mapping", "untyped_row"))
def test_untyped_host_projection_is_rejected_before_content_generation(key: str, bad: str) -> None:
    value = {} if bad == "mapping" else ({"id": "synthetic-untyped"},)
    with pytest.raises(ReportError):
        report(**{key: value})


@pytest.mark.parametrize(
    "kind,day,tz",
    (
        ("daily", DAY, "Asia/Shanghai"),
        (True, DAY, "Asia/Shanghai"),
        ("weekly", datetime(2026, 10, 21), "Asia/Shanghai"),
        ("monthly", DAY, "Synthetic/Unavailable"),
        ("monthly", date(9999, 12, 1), "Asia/Shanghai"),
    ),
)
def test_invalid_period_cannot_silently_choose_a_default(kind: Any, day: Any, tz: str) -> None:
    with pytest.raises(ReportError):
        period_for(kind, day, tz)


@pytest.mark.parametrize(
    "changes",
    (
        {"scope": {"owner_id": "synthetic-untyped"}},
        {"text": ""},
        {"text": " "},
        {"text": "x" * 4001},
        {"category": "prediction"},
        {"category": True},
        {"status": "unknown"},
        {"origin": "generated_fact"},
        {"area_id": "unknown-area"},
        {"source_states": ({"source_id": "synthetic-untyped"},)},
        {"said_at": datetime(2026, 10, 21)},
    ),
)
def test_malformed_record_from_host_import_does_not_reach_report(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        report(records=(record(**changes),))


def test_conflicting_source_duplicates_and_empty_or_reversed_ranges_are_rejected() -> None:
    row = record()
    with pytest.raises(ReportError):
        record(source_states=(row.source_states[0], row.source_states[0]))
    for start, end in ((NOW, NOW), (NOW, NOW - timedelta(seconds=1)), (None, NOW)):
        with pytest.raises(ReportError):
            record(at=start, end=end)
    with pytest.raises(ReportError):
        record(valid_from=NOW, valid_to=NOW - timedelta(seconds=1))


def test_invalid_transit_and_synthetic_imports_fail_closed() -> None:
    with pytest.raises(ReportError):
        DailyTransitInput(datetime(2026, 10, 21), {})
    with pytest.raises(ReportError):
        DailyTransitInput(DAY, {}, current_state={})
    for changes in ({"scope": {}}, {"text": ""}, {"text": "x" * 2001}, {"source_states": ({},)}):
        with pytest.raises(ValueError):
            symbolic(**changes)

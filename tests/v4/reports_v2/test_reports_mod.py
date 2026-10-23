"""Synthetic content, period and revocation checks; no model, database or real notification."""

import calendar as month_calendar
import json
import random
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.application.briefing_v2 import calendar_snapshot
from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.application.reports_v2 import (
    BasisRef,
    BriefSourceState,
    DailyTransitInput,
    ReportEffects,
    ReportError,
    ReportRecord,
    SyntheticSymbolicInput,
    compose_period_report,
    period_for,
)
from mingjing_core.application.reports_v2.citations import CitationRegistry
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = FollowupScope("synthetic-owner", "synthetic-self")
FIXTURE = Path(__file__).parents[1] / "briefing_v2/fixtures/daily_transit_synthetic_20261021.json"


def record(number=1, **changes):
    body = f"合成用户原话{number}"
    ref = BasisRef("m1", f"synthetic-record-source-{number}", 1, SCOPE.owner_id, SCOPE.subject_id, fingerprint(body))
    current = BriefSourceState(ref.source_id, SCOPE, 1, ref.value_sha256)
    base = dict(
        scope=SCOPE,
        id=f"record-{number}",
        category="fact",
        text=body,
        said_at=AT - timedelta(days=1),
        at=AT - timedelta(hours=1),
        basis=(ref,),
        source_states=(current,),
    )
    base.update(changes)
    return ReportRecord(**base)


def compose(**changes):
    base = dict(scope=SCOPE, kind="monthly", day=date(2026, 10, 21), clock=FrozenClock(AT))
    base.update(changes)
    return compose_period_report(**base)


def content(report):
    return "\n".join(line.text for section in report.sections for line in section.lines)


@pytest.mark.parametrize(
    "kind,day,key,start,end",
    [
        ("weekly", "2026-10-17", "2026-W42", "2026-10-12", "2026-10-18"),
        ("weekly", "2027-01-01", "2026-W53", "2026-12-28", "2027-01-03"),
        ("monthly", "2024-02-01", "2024-02", "2024-02-01", "2024-02-29"),
        ("monthly", "2026-10-01", "2026-10", "2026-10-01", "2026-10-31"),
        ("quarterly", "2026-10-01", "2026-Q4", "2026-10-01", "2026-12-31"),
        ("quarterly", "2024-03-31", "2024-Q1", "2024-01-01", "2024-03-31"),
    ],
)
@pytest.mark.parametrize(
    "tz", ["Asia/Shanghai", "Asia/Tokyo", "UTC", "America/New_York", "Europe/Berlin", "Pacific/Auckland"]
)
def test_fixed_v3_current_periods_across_six_zones(kind, day, key, start, end, tz):
    period = period_for(kind, date.fromisoformat(day), tz)
    assert period.key == key and period.start_day.isoformat() == start and period.end_day.isoformat() == end
    assert period.start.tzinfo == UTC and period.end.tzinfo == UTC
    assert period.start.astimezone(ZoneInfo(tz)).date() == date.fromisoformat(start)
    assert (period.end - timedelta(microseconds=1)).astimezone(ZoneInfo(tz)).date() == date.fromisoformat(end)


def test_dst_week_is_seven_civil_days_with_167_elapsed_hours():
    period = period_for("weekly", date(2026, 3, 8), "America/New_York")
    assert period.days == 7 and period.end - period.start == timedelta(hours=167)


def test_thousand_period_properties_do_not_depend_on_host_timezone():
    rng = random.Random(335)
    for _ in range(1000):
        year, month = rng.randrange(2000, 2031), rng.randrange(1, 13)
        anchor = date(year, month, rng.randrange(1, month_calendar.monthrange(year, month)[1] + 1))
        kind = rng.choice(("weekly", "monthly", "quarterly"))
        period = period_for(kind, anchor, rng.choice(("Asia/Shanghai", "Asia/Tokyo", "Europe/Berlin", "UTC")))
        assert period.start_day <= anchor <= period.end_day
        assert period.days == 7 if kind == "weekly" else 28 <= period.days <= 92


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", FollowupScope("foreign-owner", "synthetic-self")),
        ("scope", FollowupScope("synthetic-owner", "foreign-subject")),
    ],
)
def test_foreign_record_has_no_omission_id_or_body_leak(field, value):
    row = record(**{field: value, "id": "FOREIGN-ID", "text": "FOREIGN-PRIVATE"})
    with pytest.raises(ReportError) as exc:
        compose(records=(row,))
    assert "FOREIGN" not in str(exc.value) and "FOREIGN" not in exc.value.reason_code


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"origin": "assistant_claim"}, "assistant_claim_is_not_user_fact"),
        ({"status": "archived"}, "record_not_active"),
        ({"status": "retired"}, "record_not_active"),
        ({"status": "deleted"}, "record_not_active"),
        ({"valid_to": AT}, "record_expired"),
        ({"valid_from": AT + timedelta(seconds=1)}, "record_not_yet_valid"),
        ({"said_at": AT + timedelta(seconds=1)}, "source_message_in_future"),
        ({"at": AT + timedelta(days=1)}, "future_event_not_observed"),
        ({"at": datetime(2026, 9, 30, tzinfo=UTC)}, "outside_report_period"),
        ({"source_states": ()}, "current_source_state_required"),
    ],
)
def test_noncurrent_or_unproven_records_are_omitted(changes, reason):
    result = compose(records=(record(**changes),))
    assert result.omissions[0].reason == reason and not result.used_record_ids
    assert "合成用户原话" not in content(result)


@pytest.mark.parametrize(
    "change", [{"revoked": True}, {"incognito": True}, {"active": False}, {"revision": 2}, {"value_sha256": "0" * 64}]
)
def test_current_manifest_recheck_removes_old_report_content(change):
    row = record()
    old = compose(records=(row,))
    new = compose(records=(replace(row, source_states=(replace(row.source_states[0], **change),)),))
    assert old.used_record_ids == (row.id,) and new.used_record_ids == ()
    assert "合成用户原话" not in content(new)


def test_facts_plans_followups_and_areas_are_separate_and_original_instants_preserved():
    rows = (
        record(1, area_id="career"),
        record(2, category="arrangement", area_id="family", at=AT + timedelta(days=2)),
        record(3, category="followup", at=AT + timedelta(days=1)),
    )
    result = compose(records=rows)
    selected = [section for section in result.sections if section.category in {"fact", "arrangement", "followup"}]
    assert [(row.category, row.area_id) for row in selected] == [
        ("fact", "career"),
        ("arrangement", "family"),
        ("followup", None),
    ]
    line = selected[0].lines[0]
    assert line.event_at == rows[0].at and line.said_at == rows[0].said_at
    assert len({citation.local_alias for citation in result.citations}) == len(result.citations)
    assert "结果未确认" in selected[1].title


def test_record_replay_is_idempotent_but_same_id_changed_content_is_rejected():
    row = record()
    assert compose(records=(row,)) == compose(records=(row, row))
    with pytest.raises(ReportError):
        compose(records=(row, replace(row, text="另一条说法")))


def transit():
    payload = json.loads(FIXTURE.read_bytes())
    scope = FollowupScope(payload["scope"]["owner_user_id"], payload["scope"]["subject_id"])
    state = BriefSourceState(payload["document_id"], scope, payload["scope"]["revision"], payload["document_id"][5:])
    return payload, scope, DailyTransitInput(date(2026, 10, 21), payload, state)


def test_one_real_contract_snapshot_never_becomes_a_full_month_forecast():
    payload, scope, row = transit()
    result = compose(scope=scope, transits=(row,), profile_revision=payload["scope"]["revision"])
    section = next(item for item in result.sections if item.category == "symbolic")
    assert len(section.lines) == 6 and result.coverage.rendered_snapshot_days == (row.day,)
    assert (
        result.coverage.period_days == 31 and "period_symbolic_coverage_incomplete_no_extrapolation" in result.warnings
    )
    assert all("北京时间12:00快照" in line.text for line in section.lines)
    assert result.used_claim_ids and all(
        c.basis.document_id and c.basis.claim_id for line in section.lines for c in line.citations
    )


@pytest.mark.parametrize("change", ["revision", "revoke", "missing", "foreign"])
def test_chart_profile_and_current_source_guard(change):
    payload, scope, row = transit()
    revision = payload["scope"]["revision"]
    if change == "revision":
        revision += 1
    elif change == "revoke":
        row = replace(row, current_state=replace(row.current_state, revoked=True))
    elif change == "missing":
        row = replace(row, current_state=None)
    else:
        scope = FollowupScope("foreign", scope.subject_id)
    if change == "foreign":
        with pytest.raises(ReportError):
            compose(scope=scope, transits=(row,), profile_revision=revision)
    else:
        result = compose(scope=scope, transits=(row,), profile_revision=revision)
        assert not result.used_claim_ids and not any(s.category == "symbolic" for s in result.sections)


def test_explicit_synthetic_input_is_labeled_and_cannot_impersonate_actual_chart_claims():
    row = record()
    fake = SyntheticSymbolicInput(
        SCOPE, "sample", date(2026, 10, 21), "此处只有接口样例", "合成规则口径", row.basis, row.source_states
    )
    result = compose(synthetic_symbolic=(fake,))
    assert "合成接口替身" in content(result) and result.coverage.synthetic_days == (fake.day,)
    assert result.used_claim_ids == () and result.coverage.rendered_snapshot_days == ()
    with pytest.raises(ValueError):
        replace(fake, synthetic=False)
    with pytest.raises(ValueError):
        replace(fake, basis=(replace(row.basis[0], claim_id="claim-" + "0" * 64),))


def test_inputs_are_immutable_and_effects_are_zero_and_usage_reminders_stay_off():
    payload, scope, row = transit()
    before = deepcopy(payload)
    result = compose(scope=scope, transits=(row,), profile_revision=payload["scope"]["revision"])
    assert payload == before and result.effects == ReportEffects()
    assert not any(word in content(result) for word in ("打卡", "连签", "每天来看", "已经聊了", "别错过"))
    assert (
        result.request_key
        == compose(scope=scope, transits=(row,), profile_revision=payload["scope"]["revision"]).request_key
    )


@pytest.mark.parametrize("delta,expected", [(timedelta(), True), (timedelta(microseconds=-1), False)])
def test_period_start_is_inclusive_for_point_event(delta, expected):
    period = period_for("monthly", date(2026, 10, 21))
    row = record(at=period.start + delta)
    assert bool(compose(records=(row,)).used_record_ids) is expected


@pytest.mark.parametrize("delta,expected", [(timedelta(), False), (timedelta(microseconds=-1), True)])
def test_period_end_is_exclusive_for_point_event(delta, expected):
    period = period_for("monthly", date(2026, 10, 21))
    row = record(category="arrangement", at=period.end + delta)
    assert bool(compose(records=(row,)).used_record_ids) is expected


@pytest.mark.parametrize("overlap,expected", [(timedelta(), False), (timedelta(microseconds=1), True)])
def test_interval_crossing_period_start_needs_nonempty_overlap(overlap, expected):
    period = period_for("monthly", date(2026, 10, 21))
    row = record(at=period.start - timedelta(days=1), end=period.start + overlap)
    assert bool(compose(records=(row,)).used_record_ids) is expected


def test_local_aliases_preserve_both_original_documents_and_reject_rebinding():
    registry = CitationRegistry()
    first = replace(record().basis[0], alias="c1", document_id="synthetic-doc-a", path="/a")
    second = replace(first, source_id="synthetic-b", document_id="synthetic-doc-b", path="/b")
    line = registry.line("仅验证跨文档别名的合成文本", (first, second))
    assert [item.local_alias for item in line.citations] == ["c1", "c2"]
    assert all(item.source_alias == "c1" for item in line.citations)
    assert [item.basis.path for item in line.citations] == ["/a", "/b"]
    with pytest.raises(ReportError):
        registry.line("禁止旧别名换绑", (replace(first, value_sha256="0" * 64),))


@pytest.mark.parametrize(
    "lag,allowed",
    [
        (timedelta(), True),
        (timedelta(minutes=15), True),
        (timedelta(minutes=15, microseconds=1), False),
        (timedelta(seconds=-1), False),
    ],
)
def test_current_calendar_is_bounded_by_actual_snapshot_time(lag, allowed):
    snapshot = calendar_snapshot(scope=SCOPE, clock=FrozenClock(AT - lag))
    result = compose(calendar=snapshot)
    assert any(section.id == "now_calendar" for section in result.sections) is allowed


def test_foreign_current_calendar_is_rejected_without_details():
    foreign = FollowupScope("FOREIGN-OWNER", SCOPE.subject_id)
    snapshot = calendar_snapshot(scope=foreign, clock=FrozenClock(AT))
    with pytest.raises(ReportError) as exc:
        compose(calendar=snapshot)
    assert "FOREIGN" not in str(exc.value) and "FOREIGN" not in exc.value.reason_code


def test_request_key_covers_original_seconds_and_not_only_minute_display():
    row = record()
    changed = replace(row, at=row.at + timedelta(seconds=1))
    assert compose(records=(row,)).request_key != compose(records=(changed,)).request_key


@pytest.mark.parametrize("kind", [None, True, "yearly", "daily", []])
def test_period_kind_does_not_coerce_invalid_or_unsupported_values(kind):
    with pytest.raises(ReportError):
        period_for(kind, date(2026, 10, 21))

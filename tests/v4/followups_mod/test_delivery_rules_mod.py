"""Frozen-clock unit boundaries; no worker, database, model, or network is invoked."""

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ProactiveNotice,
    ReceptivityState,
)
from mingjing_core.application.followups_rules import (
    SENSITIVE_PREVIEW,
    count_followups_today,
    decide_delivery,
    safe_preview,
)
from mingjing_core.timekit.clock import FrozenClock

SCOPE = FollowupScope("synthetic-owner", "self")


def clock_at(value: str, timezone: str = "Asia/Shanghai") -> FrozenClock:
    return FrozenClock(datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(timezone)))


def candidate(clock: FrozenClock, **values: object) -> FollowupCandidate:
    fields: dict[str, object] = {
        "id": "synthetic-followup",
        "owner_id": SCOPE.owner_id,
        "subject_id": SCOPE.subject_id,
        "kind": "followup",
        "due_at": clock.now() - timedelta(minutes=1),
    }
    fields.update(values)
    return FollowupCandidate(**fields)


def decide(
    clock: FrozenClock,
    *,
    settings: FollowupSettings | None = None,
    state: ReceptivityState | None = None,
    count: int = 0,
    **values: object,
):
    return decide_delivery(
        candidate(clock, **values),
        settings or FollowupSettings(),
        state or ReceptivityState(SCOPE.owner_id, SCOPE.subject_id),
        scope=SCOPE,
        clock=clock,
        sent_today=count,
    )


@pytest.mark.parametrize(
    "stamp,allowed,next_stamp",
    [
        ("2026-10-19T00:00:00", False, "2026-10-19T08:30:00"),
        ("2026-10-19T07:59:59", False, "2026-10-19T08:30:00"),
        ("2026-10-19T08:00:00", True, None),
        ("2026-10-19T08:30:00", True, None),
        ("2026-10-19T21:59:59", True, None),
        ("2026-10-19T22:00:00", False, "2026-10-20T08:30:00"),
        ("2026-10-19T23:59:59", False, "2026-10-20T08:30:00"),
    ],
)
def test_default_quiet_window_is_half_open_and_resumes_at_0830(stamp, allowed, next_stamp) -> None:
    result = decide(clock_at(stamp))
    assert result.allowed is allowed
    assert result.next_due == (clock_at(next_stamp).now() if next_stamp else None)


@pytest.mark.parametrize("count,allowed", [(0, True), (1, True), (2, False), (10, False)])
def test_non_brief_daily_cap_two(count: int, allowed: bool) -> None:
    clock = clock_at("2026-10-19T12:00:00")
    result = decide(clock, count=count)
    assert result.allowed is allowed
    if not allowed:
        assert result.reason == "daily_cap"
        assert result.next_due == clock_at("2026-10-20T08:30:00").now()


def test_brief_does_not_consume_followup_cap() -> None:
    result = decide(clock_at("2026-10-19T12:00:00"), kind="brief", count=100)
    assert result.allowed


def test_zero_cap_disables_followups_and_does_not_schedule_endless_tomorrow() -> None:
    result = decide(clock_at("2026-10-19T12:00:00"), settings=FollowupSettings(daily_cap=0))
    assert not result.allowed and result.next_due is None


def test_explicit_reminder_is_exempt_from_cap_and_global_proactive_disable() -> None:
    settings = FollowupSettings(proactive_enabled=False, followups_enabled=False)
    result = decide(
        clock_at("2026-10-19T12:00:00"), settings=settings, count=100, kind="reminder", explicit_requested=True
    )
    assert result.allowed


def test_explicit_reminder_still_respects_quiet_without_specific_time_authorisation() -> None:
    result = decide(clock_at("2026-10-19T06:00:00"), kind="reminder", explicit_requested=True)
    assert not result.allowed and result.reason == "quiet_hours"


def test_explicit_six_oclock_reminder_respects_requested_quiet_time() -> None:
    result = decide(clock_at("2026-10-19T06:00:00"), kind="reminder", explicit_requested=True, explicit_quiet_time=True)
    assert result.allowed


def test_specific_time_authorisation_does_not_send_reminder_before_due() -> None:
    clock = clock_at("2026-10-19T05:00:00")
    due = clock_at("2026-10-19T06:00:00").now()
    result = decide(clock, kind="reminder", explicit_requested=True, explicit_quiet_time=True, due_at=due)
    assert not result.allowed and result.reason == "not_due" and result.next_due == due


def test_reminder_label_without_explicit_request_does_not_gain_privileges() -> None:
    result = decide(clock_at("2026-10-19T12:00:00"), kind="reminder", count=100)
    assert not result.allowed and result.reason == "reminder_not_requested"


def test_explicit_requested_on_a_followup_does_not_bypass_cap() -> None:
    result = decide(clock_at("2026-10-19T12:00:00"), count=2, explicit_requested=True)
    assert not result.allowed and result.reason == "daily_cap"


@pytest.mark.parametrize(
    "flags,reason",
    [
        ({"source_revoked": True, "active": False}, "source_revoked"),
        ({"source_active": False}, "source_inactive"),
        ({"active": False}, "inactive"),
    ],
)
def test_source_and_active_checks_have_priority_over_every_exception(flags, reason) -> None:
    result = decide(
        clock_at("2026-10-19T06:00:00"),
        kind="reminder",
        explicit_requested=True,
        explicit_quiet_time=True,
        count=100,
        **flags,
    )
    assert not result.allowed and result.reason == reason and result.next_due is None


@pytest.mark.parametrize("from_state", [False, True])
def test_specific_category_mute_overrides_earlier_explicit_reminder(from_state: bool) -> None:
    settings = FollowupSettings(muted_categories=frozenset() if from_state else frozenset({"HEALTH"}))
    state = ReceptivityState(
        SCOPE.owner_id, SCOPE.subject_id, muted_categories=frozenset({"health"}) if from_state else frozenset()
    )
    result = decide(
        clock_at("2026-10-19T12:00:00"),
        settings=settings,
        state=state,
        category="health",
        kind="reminder",
        explicit_requested=True,
    )
    assert not result.allowed and result.reason == "category_muted"


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_candidate_and_state_are_scoped_before_decision(field: str) -> None:
    clock = clock_at("2026-10-19T12:00:00")
    with pytest.raises(ValueError):
        decide(clock, **{field: "another-scope"})
    state = replace(ReceptivityState(SCOPE.owner_id, SCOPE.subject_id), **{field: "another-scope"})
    with pytest.raises(ValueError):
        decide(clock, state=state)


@pytest.mark.parametrize("category", ["health", "wellbeing", "finance", "money", "身心", "财务", " HEALTH "])
def test_sensitive_preview_never_contains_synthetic_private_detail(category: str) -> None:
    result = decide(clock_at("2026-10-19T12:00:00"), category=category, text="合成私密健康财务标记XYZ")
    assert result.preview == SENSITIVE_PREVIEW
    assert "XYZ" not in repr(result)


def test_explicit_sensitivity_and_user_initiated_preview_have_separate_meanings() -> None:
    assert safe_preview("合成正文", "custom", sensitive=True) == SENSITIVE_PREVIEW
    assert safe_preview("合成正文", "finance", proactive=False) == "合成正文"


def test_adaptation_pause_suppresses_only_nonessential_followups() -> None:
    clock = clock_at("2026-10-19T12:00:00")
    until = clock.now() + timedelta(days=7)
    state = ReceptivityState(SCOPE.owner_id, SCOPE.subject_id, pause_until=until)
    assert not decide(clock, state=state).allowed
    assert decide(clock, state=state).next_due == until
    assert decide(clock, state=state, essential=True).allowed
    assert not decide(clock, state=state, essential=True, count=1).allowed
    assert decide(clock, state=state, kind="brief", count=100).allowed


@pytest.mark.parametrize("bad_count", [-1, True, 1.5])
def test_untrusted_day_counter_is_rejected(bad_count) -> None:
    with pytest.raises(ValueError):
        decide(clock_at("2026-10-19T12:00:00"), count=bad_count)


def test_dst_spring_cap_deferral_uses_next_local_day_not_24_utc_hours() -> None:
    clock = clock_at("2026-03-07T12:00:00", "America/New_York")
    settings = FollowupSettings(timezone="America/New_York")
    result = decide(clock, settings=settings, count=2)
    assert result.next_due == datetime(2026, 3, 8, 12, 30, tzinfo=UTC)


@pytest.mark.parametrize("fold", [0, 1])
def test_dst_fall_quiet_deferral_handles_both_repeated_hours(fold: int) -> None:
    local = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=fold)
    result = decide(FrozenClock(local), settings=FollowupSettings(timezone="America/New_York"))
    assert result.next_due == datetime(2026, 11, 1, 13, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "values",
    [
        {"daily_cap": 3},
        {"daily_cap": True},
        {"proactive_enabled": 1},
        {"resume_at": time(7)},
        {"quiet_start": time(8), "quiet_end": time(8)},
    ],
)
def test_policy_cannot_raise_design_cap_or_resume_during_quiet(values) -> None:
    with pytest.raises(ValueError):
        FollowupSettings(**values)


def test_scoped_day_counter_deduplicates_and_excludes_brief_reminder_future_and_previous_day() -> None:
    clock = clock_at("2026-10-19T09:00:00")
    sent = ProactiveNotice("sent", SCOPE.owner_id, SCOPE.subject_id, "followup", clock.now())
    records = [
        sent,
        sent,
        replace(sent, id="brief", kind="brief"),
        replace(sent, id="reminder", kind="reminder"),
        replace(sent, id="future", sent_at=clock.now() + timedelta(minutes=1)),
        replace(sent, id="yesterday", sent_at=clock.now() - timedelta(days=1)),
    ]
    assert count_followups_today(records, scope=SCOPE, clock=clock) == 1


def test_day_counter_rejects_foreign_scope_or_conflicting_same_identifier() -> None:
    clock = clock_at("2026-10-19T09:00:00")
    sent = ProactiveNotice("sent", SCOPE.owner_id, SCOPE.subject_id, "followup", clock.now())
    with pytest.raises(ValueError):
        count_followups_today([replace(sent, owner_id="another-owner")], scope=SCOPE, clock=clock)
    with pytest.raises(ValueError):
        count_followups_today([sent, replace(sent, kind="reminder")], scope=SCOPE, clock=clock)


def test_day_counter_uses_owner_calendar_day_rather_than_utc_date() -> None:
    clock = FrozenClock(datetime(2026, 10, 18, 17, tzinfo=UTC))
    records = [ProactiveNotice("today", SCOPE.owner_id, SCOPE.subject_id, "followup", clock.now())]
    assert count_followups_today(records, scope=SCOPE, clock=clock, timezone="Asia/Shanghai") == 1
    assert count_followups_today(records, scope=SCOPE, clock=clock, timezone="America/New_York") == 1
    earlier = replace(records[0], id="utc-yesterday", sent_at=clock.now() - timedelta(hours=2))
    assert count_followups_today([earlier], scope=SCOPE, clock=clock, timezone="Asia/Shanghai") == 0

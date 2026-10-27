"""Independent fixed-seed owner-time oracles, using FrozenClock and synthetic notices only."""

import random
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.followups_adaptation import apply_response, classify_response
from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ProactiveNotice,
    ReceptivityState,
    UserActivity,
)
from mingjing_core.application.followups_rules import (
    count_followups_today,
    decide_delivery,
    effective_daily_cap,
    safe_preview,
)
from mingjing_core.timekit.clock import FrozenClock

SCOPE = FollowupScope("synthetic-owner", "synthetic-subject")
ZONES = (
    "Asia/Shanghai",
    "Asia/Taipei",
    "Asia/Kathmandu",
    "America/New_York",
    "Europe/Berlin",
    "Australia/Lord_Howe",
    "Pacific/Chatham",
    "Pacific/Kiritimati",
)
SEED = 2026101907


def _notice(at: datetime, **changes: object) -> FollowupCandidate:
    notice = FollowupCandidate(
        "synthetic-notice", SCOPE.owner_id, SCOPE.subject_id, "followup", at, text="SYNTHETIC_PRIVATE_DETAIL"
    )
    return replace(notice, **changes)


def _state(**changes: object) -> ReceptivityState:
    return replace(ReceptivityState(SCOPE.owner_id, SCOPE.subject_id), **changes)


def _quiet(at: datetime, zone: str) -> bool:
    wall = at.astimezone(ZoneInfo(zone))
    minute = wall.hour * 60 + wall.minute
    return minute < 8 * 60 or minute >= 22 * 60


def _oracle_allowed(
    candidate: FollowupCandidate, settings: FollowupSettings, state: ReceptivityState, now: datetime, sent: int
) -> bool:
    if candidate.source_revoked or not candidate.source_active or not candidate.active:
        return False
    if candidate.category in settings.muted_categories | state.muted_categories:
        return False
    explicit = candidate.kind == "reminder" and candidate.explicit_requested
    if candidate.kind == "reminder" and not explicit:
        return False
    if not explicit and (
        not settings.proactive_enabled or (candidate.kind == "followup" and not settings.followups_enabled)
    ):
        return False
    paused = state.pause_until is not None and now < state.pause_until
    if candidate.kind == "followup" and paused and not candidate.essential:
        return False
    if now < candidate.due_at or (_quiet(now, settings.timezone) and not candidate.explicit_quiet_time):
        return False
    cap = min(settings.daily_cap, 1) if paused else settings.daily_cap
    return candidate.kind != "followup" or sent < cap


def test_1000_frozen_owner_time_cases_follow_independent_delivery_oracle() -> None:
    rng = random.Random(SEED)
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(1000):
        clock = FrozenClock(origin + timedelta(seconds=rng.randrange(365 * 86400)))
        kind = rng.choice(("followup", "followup", "reminder", "brief"))
        explicit = kind == "reminder" and rng.choice((True, False))
        category = rng.choice(("career", "health", "finance"))
        muted = frozenset({category}) if rng.randrange(8) == 0 else frozenset()
        settings = FollowupSettings(
            timezone=rng.choice(ZONES),
            daily_cap=rng.randrange(3),
            proactive_enabled=rng.randrange(5) != 0,
            followups_enabled=rng.randrange(5) != 0,
            muted_categories=muted,
        )
        paused = rng.randrange(4) == 0
        state = _state(pause_until=clock.now() + timedelta(days=3) if paused else None)
        candidate = _notice(
            clock.now() - timedelta(minutes=rng.randrange(720)),
            kind=kind,
            category=category,
            explicit_requested=explicit,
            explicit_quiet_time=explicit and rng.choice((True, False)),
            active=rng.randrange(7) != 0,
            source_active=rng.randrange(7) != 0,
            source_revoked=rng.randrange(9) == 0,
            essential=rng.choice((True, False)),
        )
        sent = rng.randrange(5)
        result = decide_delivery(candidate, settings, state, scope=SCOPE, clock=clock, sent_today=sent)
        assert result.allowed == _oracle_allowed(candidate, settings, state, clock.now(), sent), (SEED, index)
        assert 0 <= result.daily_cap <= settings.daily_cap <= 2, (SEED, index)
        assert effective_daily_cap(settings, state, clock=clock) == result.daily_cap
        if result.next_due is not None:
            assert result.next_due > clock.now(), (SEED, index)
        if category in {"health", "finance"}:
            assert candidate.text not in result.preview
        assert candidate.text not in repr(result) and candidate.text not in repr(candidate)


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("local_day", [date(2026, 3, 7), date(2026, 3, 28), date(2026, 10, 24), date(2026, 10, 31)])
def test_cap_deferral_uses_next_owner_day_not_fixed_twenty_four_hours(zone: str, local_day: date) -> None:
    tz = ZoneInfo(zone)
    local_noon = datetime.combine(local_day, time(12), tz)
    clock = FrozenClock(local_noon)
    result = decide_delivery(
        _notice(clock.now()), FollowupSettings(timezone=zone), _state(), scope=SCOPE, clock=clock, sent_today=2
    )
    expected = datetime.combine(local_day + timedelta(days=1), time(8, 30), tz).astimezone(UTC)
    assert not result.allowed and result.reason == "daily_cap"
    assert result.next_due == expected


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("wall", [time(0), time(7, 59, 59), time(8), time(21, 59, 59), time(22), time(23, 59, 59)])
def test_quiet_hours_are_half_open_and_resume_at_owner_eight_thirty(zone: str, wall: time) -> None:
    local = datetime.combine(date(2026, 10, 31), wall, ZoneInfo(zone))
    clock = FrozenClock(local)
    result = decide_delivery(_notice(clock.now()), FollowupSettings(timezone=zone), _state(), scope=SCOPE, clock=clock)
    quiet = wall < time(8) or wall >= time(22)
    assert result.allowed is not quiet
    if quiet:
        day = local.date() + timedelta(days=int(wall >= time(22)))
        assert result.next_due == datetime.combine(day, time(8, 30), ZoneInfo(zone)).astimezone(UTC)


@pytest.mark.parametrize("zone", ZONES)
def test_explicit_reminder_bypasses_global_pause_and_cap_but_needs_explicit_quiet_time(zone: str) -> None:
    clock = FrozenClock(datetime(2026, 10, 19, 2, tzinfo=ZoneInfo(zone)))
    settings = FollowupSettings(timezone=zone, daily_cap=0, proactive_enabled=False, followups_enabled=False)
    state = _state(pause_until=clock.now() + timedelta(days=7))
    reminder = _notice(clock.now(), kind="reminder", explicit_requested=True, explicit_quiet_time=True)
    allowed = decide_delivery(reminder, settings, state, scope=SCOPE, clock=clock, sent_today=100)
    assert allowed.allowed
    deferred = decide_delivery(
        replace(reminder, explicit_quiet_time=False), settings, state, scope=SCOPE, clock=clock, sent_today=100
    )
    assert not deferred.allowed and deferred.reason == "quiet_hours"


@pytest.mark.parametrize("changes", [{"source_revoked": True}, {"source_active": False}, {"active": False}])
def test_revocation_and_cancellation_override_explicit_reminder_exceptions(changes: dict[str, bool]) -> None:
    clock = FrozenClock(datetime(2026, 10, 19, 2, tzinfo=UTC))
    notice = _notice(clock.now(), kind="reminder", explicit_requested=True, explicit_quiet_time=True, **changes)
    result = decide_delivery(notice, FollowupSettings(), _state(), scope=SCOPE, clock=clock)
    assert not result.allowed and result.next_due is None


@pytest.mark.parametrize("muted_source", ["settings", "state"])
def test_specific_category_mute_revokes_an_older_explicit_reminder(muted_source: str) -> None:
    clock = FrozenClock(datetime(2026, 10, 19, 12, tzinfo=ZoneInfo("Asia/Shanghai")))
    settings = FollowupSettings(muted_categories=frozenset({"health"}) if muted_source == "settings" else frozenset())
    state = _state(muted_categories=frozenset({"health"}) if muted_source == "state" else frozenset())
    notice = _notice(clock.now(), kind="reminder", category="health", explicit_requested=True)
    result = decide_delivery(notice, settings, state, scope=SCOPE, clock=clock)
    assert not result.allowed and result.reason == "category_muted"


@pytest.mark.parametrize(
    "category", ["health", "wellbeing", "medical", "finance", "money", "身心", "财务", "健康", "金钱"]
)
def test_sensitive_preview_never_contains_private_details_or_category_name(category: str) -> None:
    private = f"SYNTHETIC_PRIVATE_{category}_DETAIL"
    preview = safe_preview(private, category)
    assert private not in preview and category not in preview and preview.strip()
    assert "SYNTHETIC_PRIVATE_DETAIL" not in safe_preview("SYNTHETIC_PRIVATE_DETAIL", "career", sensitive=True)


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_cross_scope_notice_or_state_is_never_eligible(field: str) -> None:
    clock = FrozenClock(datetime(2026, 10, 19, 12, tzinfo=UTC))
    notice = _notice(clock.now())
    with pytest.raises(ValueError, match="归属"):
        decide_delivery(
            replace(notice, **{field: "other-synthetic"}), FollowupSettings(), _state(), scope=SCOPE, clock=clock
        )
    with pytest.raises(ValueError, match="归属"):
        decide_delivery(notice, FollowupSettings(), _state(**{field: "other-synthetic"}), scope=SCOPE, clock=clock)


def test_default_policy_and_a_reply_cannot_raise_the_configured_cap() -> None:
    settings = FollowupSettings()
    assert settings.daily_cap == 2 and settings.quiet_start == time(22) and settings.quiet_end == time(8)
    clock = FrozenClock(datetime(2026, 10, 19, 12, tzinfo=UTC))
    assert effective_daily_cap(settings, _state(), clock=clock) == 2
    assert effective_daily_cap(replace(settings, daily_cap=1), _state(), clock=clock) == 1
    for value in (-1, 3, True, 1.0, "2"):
        with pytest.raises(ValueError):
            replace(settings, daily_cap=value)


def _response_sequence(rng: random.Random, sequence_id: int) -> None:
    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=rng.randrange(365 * 24)))
    settings = FollowupSettings(timezone=rng.choice(ZONES), daily_cap=rng.choice((1, 2)))
    state, streak, until, reset_for = _state(), 0, None, None
    for index in range(12):
        clock.advance(timedelta(minutes=rng.randrange(1, 120)))
        sent = clock.now()
        kind = rng.choice(("followup", "followup", "brief", "reminder"))
        notice = ProactiveNotice(f"sequence-{sequence_id}-{index}", SCOPE.owner_id, SCOPE.subject_id, kind, sent)
        replied = rng.randrange(3) == 0
        reply_at = sent + timedelta(minutes=rng.randrange(1, 1441))
        activities = (UserActivity(f"ack-{index}", SCOPE.owner_id, SCOPE.subject_id, reply_at),) if replied else ()
        clock.advance(timedelta(hours=24))
        status = classify_response(notice, activities, scope=SCOPE, clock=clock)
        assert status == ("replied" if replied else "ignored"), (SEED, sequence_id, index)
        if until is not None and clock.now() >= until and reset_for != until:
            streak, reset_for = 0, until
        if kind != "reminder":
            streak = min(2, streak + 1) if status == "ignored" else 0
        if streak >= 2 and (until is None or clock.now() >= until):
            until, reset_for = clock.now() + timedelta(days=7), None
        state = apply_response(state, notice, status, scope=SCOPE, clock=clock, timezone=settings.timezone)
        assert state.pause_until == until, (SEED, sequence_id, index)
        assert apply_response(state, notice, status, scope=SCOPE, clock=clock) == state
        cap = effective_daily_cap(settings, state, clock=clock)
        assert cap <= settings.daily_cap
        candidate = _notice(clock.now())
        delivery = decide_delivery(candidate, settings, state, scope=SCOPE, clock=clock)
        if until is not None and clock.now() < until:
            assert not delivery.allowed and delivery.reason == "adaptation_pause"
            reminder = replace(candidate, kind="reminder", explicit_requested=True, explicit_quiet_time=True)
            assert decide_delivery(reminder, settings, state, scope=SCOPE, clock=clock, sent_today=99).allowed


def test_1000_random_send_reply_sequences_preserve_caps_and_seven_day_pause() -> None:
    rng = random.Random(SEED + 1)
    for sequence_id in range(1000):
        _response_sequence(rng, sequence_id)


@pytest.mark.parametrize(
    "sent,elapsed_hours,expected",
    [
        (datetime(2026, 3, 7, 12, tzinfo=ZoneInfo("America/New_York")), 23.5, "replied"),
        (datetime(2026, 10, 31, 12, tzinfo=ZoneInfo("America/New_York")), 24.5, "ignored"),
    ],
)
def test_reply_window_is_twenty_four_elapsed_hours_across_dst(
    sent: datetime, elapsed_hours: float, expected: str
) -> None:
    start = sent.astimezone(UTC)
    notice = ProactiveNotice("dst-notice", SCOPE.owner_id, SCOPE.subject_id, "followup", sent)
    activity = UserActivity("dst-ack", SCOPE.owner_id, SCOPE.subject_id, start + timedelta(hours=elapsed_hours))
    clock = FrozenClock(start + timedelta(hours=26))
    assert classify_response(notice, (activity,), scope=SCOPE, clock=clock) == expected


def test_ignored_cannot_be_finalized_before_elapsed_deadline_across_spring_dst() -> None:
    sent = datetime(2026, 3, 7, 12, tzinfo=ZoneInfo("America/New_York"))
    notice = ProactiveNotice("dst-early", SCOPE.owner_id, SCOPE.subject_id, "followup", sent)
    clock = FrozenClock(sent.astimezone(UTC) + timedelta(hours=23, minutes=30))
    assert classify_response(notice, (), scope=SCOPE, clock=clock) == "pending"
    with pytest.raises(ValueError, match="24"):
        apply_response(_state(), notice, "ignored", scope=SCOPE, clock=clock)


def test_1000_random_sent_ledgers_count_only_unique_current_owner_day_followups() -> None:
    rng = random.Random(SEED + 2)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(1000):
        clock = FrozenClock(base + timedelta(seconds=rng.randrange(365 * 86400)))
        zone = rng.choice(ZONES)
        day = clock.now().astimezone(ZoneInfo(zone)).date()
        notices, expected = [], 0
        for row in range(15):
            at = clock.now() + timedelta(minutes=rng.randrange(-3000, 120))
            kind = rng.choice(("followup", "brief", "reminder"))
            notice = ProactiveNotice(f"ledger-{index}-{row}", SCOPE.owner_id, SCOPE.subject_id, kind, at)
            notices.extend((notice, replace(notice)))
            expected += int(kind == "followup" and at <= clock.now() and at.astimezone(ZoneInfo(zone)).date() == day)
        rng.shuffle(notices)
        assert count_followups_today(notices, scope=SCOPE, clock=clock, timezone=zone) == expected, (SEED, index)


@pytest.mark.parametrize("seconds,expected", [(0, "ignored"), (1, "replied"), (86400, "replied"), (86401, "ignored")])
def test_response_window_is_open_at_send_and_closed_at_elapsed_deadline(seconds: int, expected: str) -> None:
    at = datetime(2026, 10, 19, 12, tzinfo=UTC)
    notice = ProactiveNotice("boundary", SCOPE.owner_id, SCOPE.subject_id, "followup", at)
    activity = UserActivity("boundary-ack", SCOPE.owner_id, SCOPE.subject_id, at + timedelta(seconds=seconds))
    clock = FrozenClock(at + timedelta(hours=25))
    assert classify_response(notice, (activity,), scope=SCOPE, clock=clock) == expected


def test_explicit_disable_keeps_usage_reminder_off_with_three_hours_of_continuous_messages() -> None:
    from mingjing_core.application.usage_guard_rules import UsageEvent, UsagePolicy, UsageState, usage_decision

    clock = FrozenClock(datetime(2026, 10, 19, 4, tzinfo=UTC))
    events = [
        UsageEvent(f"usage-{minute}", SCOPE.owner_id, clock.now() - timedelta(minutes=minute))
        for minute in range(0, 181, 5)
    ]
    assert UsagePolicy().enabled is True
    result = usage_decision(events, UsageState(SCOPE.owner_id), clock=clock, policy=UsagePolicy(enabled=False))
    assert not result.should_remind and result.reason == "disabled"

"""K1/K2 exact boundaries, current-claim guards and frozen-clock random invariants."""

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from random import Random
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.application.followups_rules import SENSITIVE_PREVIEW, in_quiet_hours
from mingjing_core.scheduling.delivery_contracts import DeliveryRequest
from mingjing_core.scheduling.delivery_rules import plan_delivery, recheck_delivery
from mingjing_core.timekit.clock import FrozenClock

SCOPE = FollowupScope("synthetic-owner", "self")
SETTINGS = FollowupSettings()
STATE = ReceptivityState(SCOPE.owner_id, SCOPE.subject_id)


def stamp(text):
    return datetime.fromisoformat(text + "+08:00").astimezone(UTC)


def request(due, *, kind="reminder", occurrence="synthetic-occurrence", subscribed=False, not_before=None, **kwargs):
    candidate = FollowupCandidate(
        "synthetic-candidate",
        SCOPE.owner_id,
        SCOPE.subject_id,
        kind,
        due,
        explicit_requested=kind == "reminder",
        text="合成提醒正文",
        **kwargs,
    )
    return DeliveryRequest(occurrence, candidate, due, subscribed, not_before)


def decide(item, now, *, settings=SETTINGS, state=STATE, count=0):
    return plan_delivery(item, settings, state, scope=SCOPE, clock=FrozenClock(now), sent_today=count)


@pytest.mark.parametrize(
    "seconds,disposition",
    [
        (0, "push"),
        (1, "push"),
        (3599.999999, "push"),
        (3600, "push"),
        (3600.000001, "deferred"),
        (43200, "deferred"),
        (43200.000001, "app_inbox"),
    ],
)
def test_quiet_reminder_exact_lateness_thresholds(seconds, disposition):
    now = stamp("2026-10-21T02:00:00")
    item = request(now - timedelta(seconds=seconds))
    result = decide(item, now)
    assert result.disposition == disposition
    assert result.original_due == item.original_due and item.candidate.due_at == item.original_due
    assert result.late_seconds == pytest.approx(seconds)
    if disposition == "push" and seconds > 0:
        assert "晚了" in result.late_note and "分钟" in result.late_note
    if disposition == "deferred":
        assert result.next_attempt_at == stamp("2026-10-21T08:00:00")


@pytest.mark.parametrize("delta,allowed", [(timedelta(0), True), (timedelta(microseconds=1), False)])
def test_twelve_hour_limit_uses_exact_seconds_outside_quiet(delta, allowed):
    due = stamp("2026-10-21T07:00:00")
    result = decide(request(due), due + timedelta(hours=12) + delta)
    assert result.allowed is allowed and result.app_inbox_only is not allowed


def test_claim_of_a_deferred_reminder_recomputes_age_from_original_due():
    due = stamp("2026-10-20T19:30:00")
    item = request(due)
    waiting = decide(item, stamp("2026-10-21T00:45:00"))
    assert waiting.next_due == stamp("2026-10-21T08:00:00")
    retry = replace(item, not_before=waiting.next_due)
    claimed = recheck_delivery(waiting, retry, SETTINGS, STATE, scope=SCOPE, clock=FrozenClock(waiting.next_due))
    assert claimed.app_inbox_only and not claimed.allowed and claimed.late_seconds == 45000
    assert claimed.original_due == due and retry.candidate.due_at == due


def test_original_due_cannot_be_overwritten_with_retry_time():
    due = stamp("2026-10-20T19:30:00")
    item = request(due)
    with pytest.raises(ValueError, match="original_due"):
        replace(item, candidate=replace(item.candidate, due_at=stamp("2026-10-21T08:00:00")))


def test_not_due_and_retry_not_before_never_push_early():
    due = stamp("2026-10-21T23:00:00")
    assert decide(request(due), due - timedelta(microseconds=1)).disposition == "not_due"
    item = request(due, not_before=due + timedelta(minutes=10))
    result = decide(item, due + timedelta(minutes=1))
    assert result.disposition == "deferred" and result.reason == "retry_not_due"
    assert result.next_due == item.not_before


def test_original_age_expiry_cannot_be_hidden_by_a_later_retry_not_before():
    due = stamp("2026-10-20T12:00:00")
    item = request(due, not_before=due + timedelta(days=2))
    assert decide(item, due + timedelta(hours=13)).app_inbox_only


def test_subscribed_brief_at_seven_is_quiet_exempt_without_becoming_a_reminder():
    due = stamp("2026-10-21T07:00:00")
    item = request(due, kind="brief", subscribed=True)
    result = decide(item, due, count=999)
    assert result.allowed and result.kind == "brief" and item.candidate.kind == "brief"
    assert not decide(replace(item, brief_subscribed=False), due).allowed
    assert not decide(item, due, settings=replace(SETTINGS, proactive_enabled=False)).allowed
    sensitive = replace(item, candidate=replace(item.candidate, category="health"))
    assert not decide(sensitive, due, settings=replace(SETTINGS, muted_categories=frozenset({"health"}))).allowed


def test_custom_quiet_window_and_ordinary_followup_resume_are_preserved():
    now = stamp("2026-10-21T02:00:00")
    due = now - timedelta(hours=2)
    custom = replace(SETTINGS, quiet_end=time(9), resume_at=time(9, 30))
    assert decide(request(due), now, settings=custom).next_due == stamp("2026-10-21T09:00:00")
    assert decide(request(due, kind="followup"), now).next_due == stamp("2026-10-21T08:30:00")


@pytest.mark.parametrize("flag,value", [("source_revoked", True), ("source_active", False), ("active", False)])
def test_claim_rechecks_source_permissions_and_inactive_status(flag, value):
    due = stamp("2026-10-21T12:00:00")
    item = request(due)
    plan = decide(item, due)
    current = replace(item, candidate=replace(item.candidate, **{flag: value}))
    checked = recheck_delivery(plan, current, SETTINGS, STATE, scope=SCOPE, clock=FrozenClock(due))
    assert checked.disposition == "blocked" and not checked.app_inbox_only


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", "换掉后的合成正文"),
        ("category", "health"),
        ("sensitive", True),
        ("essential", True),
        ("explicit_requested", False),
        ("kind", "brief"),
        ("id", "different"),
        ("owner_id", "other"),
    ],
)
def test_claim_cannot_change_occurrence_payload(field, value):
    due = stamp("2026-10-21T12:00:00")
    item = request(due)
    plan = decide(item, due)
    current = replace(item, candidate=replace(item.candidate, **{field: value}))
    with pytest.raises(ValueError):
        recheck_delivery(plan, current, SETTINGS, STATE, scope=SCOPE, clock=FrozenClock(due))


def test_claim_rechecks_counts_global_disable_and_receptivity_pause():
    due = stamp("2026-10-21T12:00:00")
    item = request(due, kind="followup")
    plan = decide(item, due, count=1)
    assert plan.allowed
    counts = recheck_delivery(plan, item, SETTINGS, STATE, scope=SCOPE, clock=FrozenClock(due), sent_today=2)
    disabled = recheck_delivery(
        plan, item, replace(SETTINGS, proactive_enabled=False), STATE, scope=SCOPE, clock=FrozenClock(due)
    )
    paused = replace(STATE, pause_until=due + timedelta(days=7))
    adaptive = recheck_delivery(plan, item, SETTINGS, paused, scope=SCOPE, clock=FrozenClock(due))
    assert not counts.allowed and counts.reason == "daily_cap"
    assert not disabled.allowed and disabled.reason == "proactive_disabled"
    assert not adaptive.allowed and adaptive.reason == "adaptation_pause" and adaptive.daily_cap == 1


def test_sensitive_preview_remains_redacted_for_late_explicit_reminder():
    due = stamp("2026-10-21T23:00:00")
    item = request(due, category="health", sensitive=True)
    result = decide(item, due + timedelta(minutes=15))
    assert result.allowed and result.preview == SENSITIVE_PREVIEW
    assert result.late_note == "晚了 15 分钟" and item.candidate.text not in repr(result)


@pytest.mark.parametrize(
    "field,value",
    [("brief_subscribed", 1), ("original_due", datetime(2026, 10, 21)), ("occurrence_id", ""), ("occurrence_id", 1)],
)
def test_delivery_request_rejects_malformed_contracts(field, value):
    item = request(stamp("2026-10-21T12:00:00"))
    with pytest.raises(ValueError):
        replace(item, **{field: value})


@pytest.mark.parametrize("seed", range(1000))
def test_frozen_random_delivery_never_weakens_legacy_guards_or_lateness(seed):
    rng = Random(4216021 + seed)
    now = stamp("2026-10-21T00:00:00") + timedelta(seconds=rng.randint(0, 172800))
    age = rng.randint(-3600, 72000)
    kind = rng.choice(("followup", "brief", "reminder"))
    valid = rng.choice((True, True, False))
    revoked = rng.choice((False, False, True))
    active = rng.choice((True, True, False))
    settings = replace(SETTINGS, daily_cap=rng.randint(0, 2), proactive_enabled=rng.choice((True, False)))
    subscribed = kind == "brief" and rng.choice((True, False))
    item = request(
        now - timedelta(seconds=age),
        kind=kind,
        subscribed=subscribed,
        source_active=valid,
        source_revoked=revoked,
        active=active,
    )
    result = decide(item, now, settings=settings, count=rng.randint(0, 5))
    if revoked or not valid or not active:
        assert result.disposition == "blocked"
    if not settings.proactive_enabled and kind != "reminder":
        assert not result.allowed
    if kind == "brief" and not subscribed:
        assert not result.allowed
    if result.allowed:
        assert age >= 0 and valid and active and not revoked
        quiet = in_quiet_hours(now.astimezone(ZoneInfo(settings.timezone)).timetz(), settings)
        if kind == "reminder":
            assert age <= 43200 and (not quiet or age <= 3600)
        elif kind != "brief":
            assert not quiet
    assert item.original_due == item.candidate.due_at == result.original_due

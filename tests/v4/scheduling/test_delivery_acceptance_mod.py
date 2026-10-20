"""K1/K2 intent truth, fresh claim authorization and independent randomized safety invariants."""

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.scheduling.delivery_contracts import DeliveryRequest
from mingjing_core.scheduling.delivery_rules import plan_delivery, recheck_delivery
from mingjing_core.timekit.clock import FrozenClock

TRUTH = json.loads((Path(__file__).parent / "fixtures/delivery_expected_mod.json").read_bytes())
SCOPE = FollowupScope("owner", "self")
SETTINGS = FollowupSettings()
STATE = ReceptivityState("owner", "self")
AT = datetime(2026, 10, 21, tzinfo=ZoneInfo("Asia/Shanghai"))


def request(kind="reminder", due=AT, *, subscribed=False, not_before=None, **changes):
    candidate = FollowupCandidate(
        "notice",
        "owner",
        "self",
        kind,
        due,
        text="合成安排正文",
        explicit_requested=kind == "reminder",
    )
    candidate = replace(candidate, **changes)
    return DeliveryRequest("occurrence", candidate, due, brief_subscribed=subscribed, not_before=not_before)


def decide(item, now, settings=SETTINGS, state=STATE, sent=0):
    return plan_delivery(item, settings, state, scope=SCOPE, clock=FrozenClock(now), sent_today=sent)


@pytest.mark.parametrize("case", TRUTH["cases"], ids=lambda case: case["id"])
def test_frozen_k1_k2_boundaries_are_exact_not_rounded_minutes(case):
    due, now = datetime.fromisoformat(case["due"]), datetime.fromisoformat(case["now"])
    item = request(case["kind"], due, subscribed=case.get("brief_subscribed", False))
    plan = decide(item, now)
    assert plan.disposition == case["disposition"]
    assert plan.allowed == (case["disposition"] == "push")
    assert plan.app_inbox_only == (case["disposition"] == "app_inbox")
    assert plan.original_due == due
    if "next_due" in case:
        assert plan.next_due == datetime.fromisoformat(case["next_due"])
    if "late_seconds" in case:
        assert plan.late_seconds == case["late_seconds"]
    if case["kind"] == "reminder" and plan.allowed and now > due:
        assert "晚了" in plan.late_note


def test_night_postponement_does_not_reset_original_age_at_claim():
    due = datetime.fromisoformat("2026-10-21T20:00:00+08:00")
    clock = FrozenClock(datetime.fromisoformat("2026-10-21T23:00:00+08:00"))
    item = request(due=due)
    plan = plan_delivery(item, SETTINGS, STATE, scope=SCOPE, clock=clock)
    assert plan.next_due == datetime.fromisoformat("2026-10-22T08:00:00+08:00")
    deferred = replace(item, not_before=plan.next_due)
    clock.advance(plan.next_due - clock.now())
    at_boundary = recheck_delivery(plan, deferred, SETTINGS, STATE, scope=SCOPE, clock=clock)
    assert at_boundary.allowed and at_boundary.late_seconds == 43200
    clock.advance(timedelta(microseconds=1))
    expired = recheck_delivery(plan, deferred, SETTINGS, STATE, scope=SCOPE, clock=clock)
    assert expired.app_inbox_only and not expired.allowed
    assert expired.original_due == due
    with pytest.raises(ValueError):
        replace(item, candidate=replace(item.candidate, due_at=plan.next_due))
    retimed = replace(
        item,
        candidate=replace(item.candidate, due_at=clock.now()),
        original_due=clock.now(),
    )
    with pytest.raises(ValueError):
        recheck_delivery(plan, retimed, SETTINGS, STATE, scope=SCOPE, clock=clock)


def test_retry_gate_never_turns_an_expired_reminder_into_a_new_due_occurrence():
    item = request(due=AT, not_before=None)
    future_gate = replace(item, not_before=AT + timedelta(days=2))
    plan = decide(future_gate, AT + timedelta(hours=13))
    assert plan.app_inbox_only and not plan.allowed
    assert plan.original_due == AT


@pytest.mark.parametrize(
    "field,value",
    [("source_active", False), ("source_revoked", True), ("active", False)],
)
def test_claim_time_rechecks_source_flags_and_cancellation(field, value):
    item = request(due=AT)
    plan = decide(item, AT)
    changed = replace(item, candidate=replace(item.candidate, **{field: value}))
    fresh = recheck_delivery(plan, changed, SETTINGS, STATE, scope=SCOPE, clock=FrozenClock(AT))
    assert fresh.disposition == "blocked" and not fresh.allowed and not fresh.app_inbox_only


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", "更换过的正文"),
        ("category", "finance"),
        ("kind", "followup"),
        ("sensitive", True),
        ("essential", True),
        ("explicit_requested", False),
    ],
)
def test_same_occurrence_cannot_swap_payload_between_schedule_and_claim(field, value):
    item = request(due=AT)
    plan = decide(item, AT)
    forged = replace(item, candidate=replace(item.candidate, **{field: value}))
    with pytest.raises(ValueError):
        recheck_delivery(plan, forged, SETTINGS, STATE, scope=SCOPE, clock=FrozenClock(AT))


def test_occurrence_and_scope_cannot_be_changed_after_planning():
    item = request(due=AT)
    plan = decide(item, AT)
    with pytest.raises(ValueError):
        recheck_delivery(
            plan,
            replace(item, occurrence_id="other"),
            SETTINGS,
            STATE,
            scope=SCOPE,
            clock=FrozenClock(AT),
        )
    with pytest.raises(ValueError):
        recheck_delivery(
            plan,
            item,
            SETTINGS,
            STATE,
            scope=FollowupScope("other", "self"),
            clock=FrozenClock(AT),
        )


def test_claim_recomputes_daily_cap_muting_and_subscription_from_live_state():
    now = AT + timedelta(hours=12)
    followup = request("followup", now)
    plan = decide(followup, now, sent=1)
    assert plan.allowed
    fresh = recheck_delivery(
        plan,
        followup,
        SETTINGS,
        STATE,
        scope=SCOPE,
        clock=FrozenClock(now),
        sent_today=2,
    )
    assert not fresh.allowed and fresh.reason == "daily_cap"
    brief = request("brief", now, subscribed=True)
    initial = decide(brief, now)
    assert initial.allowed
    assert not recheck_delivery(
        initial,
        replace(brief, brief_subscribed=False),
        SETTINGS,
        STATE,
        scope=SCOPE,
        clock=FrozenClock(now),
    ).allowed
    private = request(due=now, category="health")
    initial = decide(private, now)
    muted = replace(SETTINGS, muted_categories=frozenset({"health"}))
    assert not recheck_delivery(initial, private, muted, STATE, scope=SCOPE, clock=FrozenClock(now)).allowed


@pytest.mark.parametrize("kind", ["brief", "reminder"])
@pytest.mark.parametrize(
    "field,value",
    [("source_active", False), ("source_revoked", True), ("active", False)],
)
def test_quiet_exemption_never_bypasses_source_or_cancellation(kind, field, value):
    now = AT + timedelta(hours=7)
    item = request(kind, now, subscribed=kind == "brief", **{field: value})
    plan = decide(item, now)
    assert plan.disposition == "blocked"


def test_brief_remains_opt_in_and_explicit_reminder_ignores_followup_cap_and_general_pause():
    now = AT + timedelta(hours=7)
    assert decide(request("brief", now), now).disposition == "blocked"
    settings = replace(SETTINGS, daily_cap=0, proactive_enabled=False, followups_enabled=False)
    state = replace(STATE, pause_until=now + timedelta(days=7))
    assert decide(request(due=now), now, settings, state, sent=99).allowed
    assert not decide(request("brief", now, subscribed=True), now, settings, state).allowed


def test_sensitive_lock_screen_preview_never_contains_content_even_in_late_reminder():
    item = request(due=AT, category="health", text="合成健康私密标记")
    plan = decide(item, AT + timedelta(minutes=50))
    assert plan.allowed and plan.preview == "明镜想问问你"
    assert "合成健康私密标记" not in plan.preview + plan.late_note
    assert "合成健康私密标记" not in repr(plan)


def independent_allowed(item, settings, state, now, sent):
    c = item.candidate
    explicit = c.kind == "reminder" and c.explicit_requested
    if not c.active or not c.source_active or c.source_revoked:
        return False
    if c.category in settings.muted_categories | state.muted_categories:
        return False
    if c.kind == "reminder" and not explicit or c.kind == "brief" and not item.brief_subscribed:
        return False
    if not explicit and (not settings.proactive_enabled or c.kind == "followup" and not settings.followups_enabled):
        return False
    paused = state.pause_until is not None and now < state.pause_until
    if c.kind == "followup" and paused and not c.essential:
        return False
    if now < item.original_due or item.not_before is not None and now < item.not_before:
        return False
    local = now.astimezone(ZoneInfo(settings.timezone))
    quiet = local.hour >= 22 or local.hour < 8
    if explicit:
        late = (now - item.original_due).total_seconds()
        return late <= 43200 and (late <= 3600 or not quiet)
    if c.kind == "brief":
        return True
    cap = min(settings.daily_cap, 1) if paused else settings.daily_cap
    return not quiet and sent < cap


@pytest.mark.parametrize("seed", range(50))
def test_1000_frozen_clock_random_k1_k2_old_safety_cases(seed):
    rng = Random(574239 + seed)
    for _ in range(20):
        now = AT + timedelta(seconds=rng.randrange(30 * 86400))
        kind = rng.choice(("brief", "reminder", "followup"))
        due = now + timedelta(seconds=rng.randrange(-50000, 3600))
        settings = replace(
            SETTINGS,
            daily_cap=rng.randrange(3),
            proactive_enabled=rng.choice((True, False)),
            followups_enabled=rng.choice((True, False)),
            muted_categories=frozenset({"career"}) if rng.randrange(8) == 0 else frozenset(),
        )
        state = replace(
            STATE,
            pause_until=now + timedelta(days=2) if rng.randrange(3) == 0 else None,
        )
        item = request(
            kind,
            due,
            subscribed=kind == "brief" and rng.choice((True, False)),
            active=rng.randrange(8) != 0,
            source_active=rng.randrange(8) != 0,
            source_revoked=rng.randrange(9) == 0,
            category="career",
            essential=rng.choice((True, False)),
        )
        if rng.randrange(5) == 0:
            item = replace(item, not_before=max(due, now + timedelta(minutes=10)))
        sent = rng.randrange(4)
        plan = decide(item, now, settings, state, sent)
        assert plan.allowed == independent_allowed(item, settings, state, now, sent), (
            seed,
            kind,
            now,
            due,
        )
        assert 0 <= plan.daily_cap <= settings.daily_cap <= 2
        if plan.allowed and kind == "reminder":
            assert now - due <= timedelta(hours=12)
        assert plan.original_due == due

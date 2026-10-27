"""Frozen-clock metamorphic recurrence checks and explicit duration boundaries."""

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.application.divination_rules import DivinationScope, DivinationTurn, repetition_decision
from mingjing_core.application.usage_guard_rules import UsageEvent, UsagePolicy, UsageState, usage_decision
from mingjing_core.timekit.clock import FrozenClock

NOW = datetime(2026, 10, 19, 6, tzinfo=UTC)
SCOPE = DivinationScope("owner", "self", "life:self")


def turn(ident: str, age: float, *, scope: DivinationScope = SCOPE, tag: str = "event-a") -> DivinationTurn:
    return DivinationTurn(ident, scope, NOW - timedelta(hours=age), "合成命运追问", tag, True)


def test_second_question_reuses_real_alias_and_third_disables_new_tarot() -> None:
    current = turn("current", 0)
    first = replace(turn("first", 1), reference_alias="draw_1")
    second = repetition_decision(current, [first], clock=FrozenClock(NOW))
    assert second.occurrence == 2 and second.mode == "repeat"
    assert second.reference_alias == "draw_1" and not second.allow_new_conclusion
    third = repetition_decision(current, [first, turn("second", 0.5)], clock=FrozenClock(NOW))
    assert third.occurrence == 3 and third.mode == "reframe"
    assert not third.expose_tarot_start and not third.allow_new_conclusion
    assert third.max_questions == 1 and third.max_actions == 2


def test_1000_random_scoped_windows_are_permutation_and_replay_invariant() -> None:
    randomizer = random.Random(20261019)
    for sample in range(1000):
        records = []
        expected_ids = {"current"}
        for index in range(randomizer.randrange(1, 30)):
            scope = randomizer.choice(
                [
                    SCOPE,
                    replace(SCOPE, owner_id="other"),
                    replace(SCOPE, subject_id="other"),
                    replace(SCOPE, thread_id="incognito:other"),
                ]
            )
            tag = randomizer.choice(["event-a", "event-b"])
            age = randomizer.choice([0, 0.1, 23.99, 24, 24.01, 48])
            record = replace(
                turn(f"r{sample}-{index}", age, scope=scope, tag=tag),
                active=randomizer.choice([True, True, False]),
                source_revoked=randomizer.choice([False, False, True]),
            )
            records.append(record)
            if scope == SCOPE and tag == "event-a" and age < 24 and record.active and not record.source_revoked:
                expected_ids.add(record.id)
        current = turn("current", 0)
        result = repetition_decision(current, records, clock=FrozenClock(NOW))
        assert result.occurrence == len(expected_ids)
        randomizer.shuffle(records)
        assert repetition_decision(current, [*records, current], clock=FrozenClock(NOW)) == result
        if result.occurrence >= 3:
            assert not result.expose_tarot_start and not result.allow_new_conclusion
        assert all(value not in repr(result) for value in ("合成命运追问",))


def events(minutes: int, end: datetime = NOW) -> list[UsageEvent]:
    start = end - timedelta(minutes=minutes)
    return [UsageEvent(f"u{index}", "owner", start + timedelta(minutes=index)) for index in range(0, minutes + 1, 5)]


def test_current_d4_enables_usage_reminders_by_default() -> None:
    assert usage_decision(events(180), UsageState("owner"), clock=FrozenClock(NOW)).should_remind
    assert UsagePolicy().enabled is True


def test_strictly_more_than_two_hours_and_two_hour_cooldown() -> None:
    policy = UsagePolicy(enabled=True)
    assert not usage_decision(events(120), UsageState("owner"), clock=FrozenClock(NOW), policy=policy).should_remind
    once = usage_decision(events(130), UsageState("owner"), clock=FrozenClock(NOW), policy=policy)
    assert once.should_remind and once.continuous_minutes == 130
    later = NOW + timedelta(minutes=20)
    again = usage_decision(events(150, later), once.next_state, clock=FrozenClock(later), policy=policy)
    assert not again.should_remind and again.reason == "cooldown"


def test_crisis_and_confirmation_never_inject_a_reminder_in_the_middle() -> None:
    policy = UsagePolicy(enabled=True)
    assert not usage_decision(
        events(130), UsageState("owner"), clock=FrozenClock(NOW), policy=policy, crisis=True
    ).should_remind
    deferred = usage_decision(
        events(130), UsageState("owner"), clock=FrozenClock(NOW), policy=policy, confirming_data=True
    )
    assert not deferred.should_remind and deferred.reason == "confirmation_deferred"
    done = usage_decision(events(130), deferred.next_state, clock=FrozenClock(NOW), policy=policy)
    assert done.should_remind and done.next_state.deferred_on is None


def test_exact_ten_minute_gap_and_civil_midnight_reset_session() -> None:
    policy = UsagePolicy(enabled=True)
    interrupted = [*events(130)[:-2], UsageEvent("last", "owner", NOW)]
    assert not usage_decision(interrupted, UsageState("owner"), clock=FrozenClock(NOW), policy=policy).should_remind
    cross_midnight = datetime(2026, 10, 18, 16, 30, tzinfo=UTC)
    decision = usage_decision(
        events(150, cross_midnight),
        UsageState("owner"),
        clock=FrozenClock(cross_midnight),
        timezone="Asia/Shanghai",
        policy=policy,
    )
    assert decision.continuous_minutes == 30 and not decision.should_remind


@pytest.mark.parametrize("remaining", [[], [UsageEvent("new-session", "owner", NOW)]])
def test_deferred_reminder_is_cancelled_after_session_break(remaining: list[UsageEvent]) -> None:
    policy = UsagePolicy(enabled=True)
    deferred = usage_decision(
        events(130), UsageState("owner"), clock=FrozenClock(NOW), policy=policy, confirming_data=True
    )
    later = FrozenClock(NOW + timedelta(minutes=10))
    result = usage_decision(remaining, deferred.next_state, clock=later, policy=policy)
    assert not result.should_remind and result.continuous_minutes == 0
    assert result.next_state.deferred_on is None and result.next_state.deferred_session_start is None


def test_unbound_old_pending_state_cannot_create_zero_minute_reminder() -> None:
    result = usage_decision(
        [], UsageState("owner", deferred_on=NOW.date()), clock=FrozenClock(NOW), policy=UsagePolicy(enabled=True)
    )
    assert not result.should_remind and result.next_state.deferred_on is None


@pytest.mark.parametrize(
    "change",
    [{"owner_id": ""}, {"id": ""}, {"interactive": "false"}, {"at": datetime(2026, 10, 19)}, {"at": "not-a-time"}],
)
def test_usage_event_rejects_ambiguous_boundary_values(change: dict) -> None:
    with pytest.raises(ValueError):
        replace(UsageEvent("id", "owner", NOW), **change)


@pytest.mark.parametrize("field_name", ["active", "source_revoked", "fate_query"])
def test_repetition_state_flags_are_strict_booleans(field_name: str) -> None:
    with pytest.raises(ValueError):
        replace(turn("current", 0), **{field_name: "false"})


def test_other_owner_or_passive_notifications_cannot_inflate_usage() -> None:
    policy = UsagePolicy(enabled=True)
    history = [replace(event, owner_id="other") for event in events(130)]
    history += [replace(event, id="passive-" + event.id, interactive=False) for event in events(130)]
    assert usage_decision(history, UsageState("owner"), clock=FrozenClock(NOW), policy=policy).continuous_minutes == 0


@pytest.mark.parametrize("minutes", [0, -1, True, 2.5])
def test_usage_policy_requires_positive_integer_limits(minutes: object) -> None:
    with pytest.raises(ValueError):
        UsagePolicy(minutes=minutes)

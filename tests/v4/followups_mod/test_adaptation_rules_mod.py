"""Response-window and frequency-state transitions from fixed synthetic events only."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.application.followups_adaptation import (
    BRIEF_PROMPT_OPTIONS,
    apply_response,
    brief_prompt_due,
    classify_response,
    mark_brief_prompted,
)
from mingjing_core.application.followups_contracts import (
    FollowupScope,
    FollowupSettings,
    ProactiveNotice,
    ReceptivityState,
    UserActivity,
)
from mingjing_core.application.followups_rules import effective_daily_cap
from mingjing_core.timekit.clock import FrozenClock

SCOPE = FollowupScope("synthetic-owner", "self")
START = datetime(2026, 10, 1, 4, tzinfo=UTC)


def initial() -> ReceptivityState:
    return ReceptivityState(SCOPE.owner_id, SCOPE.subject_id)


def notice(
    ident: str, sent_at: datetime = START, *, kind: str = "followup", category: str = ""
) -> ProactiveNotice:
    return ProactiveNotice(
        ident, SCOPE.owner_id, SCOPE.subject_id, kind, sent_at, category
    )


def activity(at: datetime) -> UserActivity:
    return UserActivity("synthetic-user-message", SCOPE.owner_id, SCOPE.subject_id, at)


def ignore(
    state: ReceptivityState, clock: FrozenClock, ident: str, *, kind: str = "followup"
) -> ReceptivityState:
    sent = clock.now() - timedelta(hours=24)
    return apply_response(
        state, notice(ident, sent, kind=kind), "ignored", scope=SCOPE, clock=clock
    )


@pytest.mark.parametrize(
    "hours,status",
    [(0, "pending"), (23.999, "pending"), (24, "ignored"), (25, "ignored")],
)
def test_no_reply_response_window_uses_exact_24_hours(
    hours: float, status: str
) -> None:
    clock = FrozenClock(START + timedelta(hours=hours))
    assert classify_response(notice("n1"), [], scope=SCOPE, clock=clock) == status


@pytest.mark.parametrize(
    "hours,status",
    [
        (0, "ignored"),
        (0.001, "replied"),
        (23.999, "replied"),
        (24, "replied"),
        (24.001, "ignored"),
    ],
)
def test_any_message_counts_only_after_send_and_within_closed_24_hour_deadline(
    hours: float, status: str
) -> None:
    clock = FrozenClock(START + timedelta(hours=25))
    result = classify_response(
        notice("n1"),
        [activity(START + timedelta(hours=hours))],
        scope=SCOPE,
        clock=clock,
    )
    assert result == status


def test_future_activity_does_not_count_as_a_reply() -> None:
    clock = FrozenClock(START + timedelta(minutes=1))
    assert (
        classify_response(
            notice("n1"),
            [activity(START + timedelta(hours=1))],
            scope=SCOPE,
            clock=clock,
        )
        == "pending"
    )


def test_explicit_mute_is_distinct_from_ignored_or_replied() -> None:
    clock = FrozenClock(START + timedelta(hours=1))
    result = classify_response(
        notice("n1"),
        [activity(START + timedelta(minutes=1))],
        scope=SCOPE,
        clock=clock,
        muted_at=clock.now(),
    )
    assert result == "muted"


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_response_projection_cannot_use_another_subjects_activity(field: str) -> None:
    event = replace(activity(START + timedelta(minutes=1)), **{field: "another-scope"})
    with pytest.raises(ValueError):
        classify_response(
            notice("n1"),
            [event],
            scope=SCOPE,
            clock=FrozenClock(START + timedelta(hours=1)),
        )


def test_two_ignored_non_reminders_start_one_seven_day_pause() -> None:
    clock = FrozenClock(START + timedelta(days=1))
    first = ignore(initial(), clock, "n1")
    assert first.pause_until is None and first.ignored_streak == 1
    clock.advance(timedelta(minutes=1))
    second = ignore(first, clock, "n2")
    assert second.pause_until == clock.now() + timedelta(days=7)
    assert second.ignored_streak == 2
    assert effective_daily_cap(FollowupSettings(), second, clock=clock) == 1


def paused() -> tuple[ReceptivityState, FrozenClock]:
    clock = FrozenClock(START + timedelta(days=1))
    state = ignore(initial(), clock, "n1")
    clock.advance(timedelta(minutes=1))
    return ignore(state, clock, "n2"), clock


def test_ordinary_or_short_reply_does_not_restore_cap_early() -> None:
    state, clock = paused()
    clock.advance(timedelta(hours=1))
    replied = apply_response(
        state,
        notice("n3", clock.now() - timedelta(minutes=1)),
        "replied",
        scope=SCOPE,
        clock=clock,
    )
    assert replied.pause_until == state.pause_until
    assert effective_daily_cap(FollowupSettings(), replied, clock=clock) == 1
    assert replied.ignored_streak == 0


def test_more_ignored_messages_during_pause_do_not_keep_extending_it() -> None:
    state, clock = paused()
    clock.advance(timedelta(days=2))
    updated = ignore(state, clock, "n3")
    assert updated.pause_until == state.pause_until


def test_seven_days_recovery_is_exact_and_requires_two_new_ignores_to_pause_again() -> (
    None
):
    state, clock = paused()
    clock.advance(timedelta(days=7) - timedelta(microseconds=1))
    assert effective_daily_cap(FollowupSettings(), state, clock=clock) == 1
    clock.advance(timedelta(microseconds=1))
    assert effective_daily_cap(FollowupSettings(), state, clock=clock) == 2
    first = ignore(state, clock, "new1")
    assert first.pause_until == state.pause_until and first.ignored_streak == 1
    clock.advance(timedelta(seconds=1))
    second = ignore(first, clock, "new2")
    assert second.pause_until == clock.now() + timedelta(days=7)


def test_reminder_responses_do_not_lower_non_reminder_cap() -> None:
    clock = FrozenClock(START + timedelta(days=1))
    state = ignore(initial(), clock, "r1", kind="reminder")
    clock.advance(timedelta(minutes=1))
    state = ignore(state, clock, "r2", kind="reminder")
    assert state.pause_until is None and state.ignored_streak == 0


def test_duplicate_resolution_is_idempotent_and_does_not_slide_pause() -> None:
    state, clock = paused()
    clock.advance(timedelta(days=1))
    same = state.observations[-1].notice
    assert apply_response(state, same, "ignored", scope=SCOPE, clock=clock) is state


def test_same_message_identifier_cannot_change_metadata() -> None:
    state, clock = paused()
    changed = replace(state.observations[-1].notice, category="another-category")
    with pytest.raises(ValueError):
        apply_response(state, changed, "ignored", scope=SCOPE, clock=clock)


def test_reconciled_old_reply_keeps_an_already_started_pause() -> None:
    state, clock = paused()
    corrected = apply_response(
        state, state.observations[-1].notice, "replied", scope=SCOPE, clock=clock
    )
    assert corrected.pause_until == state.pause_until


def test_out_of_order_resolution_uses_send_order_and_keeps_historical_pause_trigger() -> (
    None
):
    clock = FrozenClock(START + timedelta(days=2))
    n1, n2, n3 = (
        notice("n1", START),
        notice("n2", START + timedelta(hours=1)),
        notice("n3", START + timedelta(hours=2)),
    )
    state = apply_response(initial(), n2, "ignored", scope=SCOPE, clock=clock)
    state = apply_response(state, n3, "replied", scope=SCOPE, clock=clock)
    state = apply_response(state, n1, "ignored", scope=SCOPE, clock=clock)
    assert state.pause_until == clock.now() + timedelta(days=7)
    assert state.ignored_streak == 0


def five_ignored_briefs() -> tuple[ReceptivityState, FrozenClock]:
    clock = FrozenClock(START + timedelta(days=1))
    state = initial()
    for day in range(5):
        state = ignore(state, clock, f"brief-{day}", kind="brief")
        if day < 4:
            clock.advance(timedelta(days=1))
    return state, clock


def test_five_consecutive_ignored_brief_days_prompt_once_in_next_dialogue() -> None:
    state, clock = five_ignored_briefs()
    assert len(state.brief_ignore_days) == 5
    assert BRIEF_PROMPT_OPTIONS == ("保持", "换个时间", "先停一周")
    assert brief_prompt_due(state, scope=SCOPE, clock=clock)
    prompted = mark_brief_prompted(state, scope=SCOPE, clock=clock)
    assert not brief_prompt_due(prompted, scope=SCOPE, clock=clock)
    with pytest.raises(ValueError):
        mark_brief_prompted(prompted, scope=SCOPE, clock=clock)


def test_further_ignored_briefs_cannot_prompt_again_within_30_days() -> None:
    state, clock = five_ignored_briefs()
    state = mark_brief_prompted(state, scope=SCOPE, clock=clock)
    prompted_at = clock.now()
    clock.advance(timedelta(days=1))
    state = ignore(state, clock, "brief-6", kind="brief")
    assert not brief_prompt_due(state, scope=SCOPE, clock=clock)
    clock.advance(timedelta(days=29) - timedelta(microseconds=1))
    assert not brief_prompt_due(state, scope=SCOPE, clock=clock)
    clock.advance(timedelta(microseconds=1))
    assert clock.now() == prompted_at + timedelta(days=30)
    assert brief_prompt_due(state, scope=SCOPE, clock=clock)


def test_five_briefs_on_one_day_are_not_five_ignored_calendar_days() -> None:
    clock = FrozenClock(START + timedelta(days=1))
    state = initial()
    for index in range(5):
        state = ignore(state, clock, f"same-day-{index}", kind="brief")
    assert len(state.brief_ignore_days) == 1
    assert not brief_prompt_due(state, scope=SCOPE, clock=clock)


def test_a_missing_brief_day_breaks_consecutive_ignored_day_streak() -> None:
    clock = FrozenClock(START + timedelta(days=1))
    state = initial()
    for index, day in enumerate((1, 2, 4, 5, 6)):
        clock = FrozenClock(START + timedelta(days=day))
        state = ignore(state, clock, f"gap-{index}", kind="brief")
    assert len(state.brief_ignore_days) == 3
    assert not state.brief_prompt_pending


def test_muted_category_is_saved_in_the_returned_projection_without_external_writes() -> (
    None
):
    clock = FrozenClock(START + timedelta(hours=1))
    muted = apply_response(
        initial(), notice("n1", category="health"), "muted", scope=SCOPE, clock=clock
    )
    assert muted.muted_categories == frozenset({"health"})
    assert not initial().muted_categories


def test_ignored_status_cannot_be_injected_before_window_expires() -> None:
    with pytest.raises(ValueError):
        apply_response(
            initial(), notice("n1"), "ignored", scope=SCOPE, clock=FrozenClock(START)
        )

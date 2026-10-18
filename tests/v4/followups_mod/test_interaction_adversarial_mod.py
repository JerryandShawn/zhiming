"""Independent P7 adversarial boundaries; genuine failures remain visible for the implementation owner."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.decision_autonomy_rules import autonomy_decision, autonomy_warnings, detect_delegation
from mingjing_core.application.divination_rules import DivinationScope, DivinationTurn, repetition_decision
from mingjing_core.application.usage_guard_rules import (
    UsageEvent,
    UsagePolicy,
    UsageState,
    usage_decision,
)
from mingjing_core.timekit.clock import FrozenClock

NOW = datetime(2026, 10, 19, 4, 0, tzinfo=UTC)
SCOPE = DivinationScope("synthetic-owner", "synthetic-subject", "life:synthetic-subject")
ENABLED = UsagePolicy(enabled=True)


def turn(
    identity: str, *, minutes_ago: float = 0, text: str = "他会不会回来找我？", **changes: object
) -> DivinationTurn:
    base = DivinationTurn(identity, SCOPE, NOW - timedelta(minutes=minutes_ago), text)
    return replace(base, **changes)


def events_between(start: datetime, end: datetime, owner: str = "synthetic-owner") -> list[UsageEvent]:
    count = int((end - start).total_seconds() // 540) + 1
    return [UsageEvent(f"synthetic-event-{i}", owner, start + timedelta(minutes=9 * i)) for i in range(count)]


@pytest.mark.parametrize(
    "offset,count", [(-timedelta(microseconds=1), 2), (timedelta(0), 1), (timedelta(microseconds=1), 1)]
)
def test_repetition_window_is_strictly_less_than_twenty_four_hours(offset: timedelta, count: int) -> None:
    previous = turn("prior", at=NOW - timedelta(hours=24) - offset)
    result = repetition_decision(turn("current"), [previous], clock=FrozenClock(NOW))
    assert result.occurrence == count


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "other-owner"),
        ("subject_id", "other-subject"),
        ("thread_id", "incognito:other-thread"),
    ],
)
def test_repetition_never_crosses_owner_subject_or_thread(field: str, value: str) -> None:
    foreign = turn("foreign", minutes_ago=1, scope=replace(SCOPE, **{field: value}))
    result = repetition_decision(turn("current"), [foreign, foreign], clock=FrozenClock(NOW))
    assert result.occurrence == 1 and result.mode == "normal"


def test_replayed_current_and_prior_sources_are_counted_once_and_history_order_does_not_choose_reference() -> None:
    prior = turn("prior", minutes_ago=10, reference_alias="draw_old")
    latest = turn("latest", minutes_ago=1, reference_alias="draw_latest")
    current = turn("current")
    result = repetition_decision(current, [latest, prior, current, prior, latest], clock=FrozenClock(NOW))
    assert result.occurrence == 3 and result.reference_alias == "draw_latest"
    assert result.mode == "reframe" and not result.expose_tarot_start and not result.allow_new_conclusion


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_replayed_source_ids_are_rejected_even_when_one_version_has_a_different_topic(
    reverse: bool,
) -> None:
    original = turn("same-source", minutes_ago=1)
    conflicting = replace(original, text="她会不会回来找我？")
    rows = [original, conflicting]
    with pytest.raises(ValueError, match="冲突"):
        repetition_decision(turn("current"), list(reversed(rows)) if reverse else rows, clock=FrozenClock(NOW))


@pytest.mark.parametrize("current_labeled", [False, True])
def test_model_canonical_label_and_rule_canonical_topic_merge_across_the_same_actor(current_labeled: bool) -> None:
    previous, current = turn("prior", minutes_ago=1), turn("current")
    if current_labeled:
        current = replace(current, topic_tag="relationship_return:他")
    else:
        previous = replace(previous, topic_tag="relationship_return:他")
    result = repetition_decision(current, [previous], clock=FrozenClock(NOW))
    assert result.occurrence == 2 and result.mode == "repeat"


def test_distinct_people_do_not_merge_just_because_the_question_has_the_same_verb() -> None:
    result = repetition_decision(
        turn("current"), [turn("other-person", text="她会不会回来找我？")], clock=FrozenClock(NOW)
    )
    assert result.occurrence == 1


def test_second_occurrence_reuses_previous_draw_and_never_authorizes_a_new_conclusion() -> None:
    prior = turn("prior", minutes_ago=60, reference_alias="draw_123")
    result = repetition_decision(turn("current"), [prior], clock=FrozenClock(NOW))
    assert result.mode == "repeat" and result.occurrence == 2
    assert result.reference_alias == "draw_123" and "第2次" in result.l3_hint
    assert not result.allow_new_conclusion and result.max_questions == 1 and result.max_actions <= 2


@pytest.mark.parametrize(
    "change",
    [
        {"active": False},
        {"source_revoked": True},
        {"at": NOW + timedelta(seconds=1)},
        {"fate_query": False},
    ],
)
def test_inactive_future_and_explicit_non_fate_history_never_increment_recurrence(change: dict[str, object]) -> None:
    prior = turn("prior", minutes_ago=1, **change)
    result = repetition_decision(turn("current"), [prior], clock=FrozenClock(NOW))
    assert result.occurrence == 1


POSITIVE_DELEGATIONS = [
    "你替我决定吧。",
    "这件事由你做主。",
    "我都听你的。",
    "你说选哪个就选哪个。",
    "按你说的选。",
    "听你的安排。",
    "全由你做主。",
    "交给你决定。",
    "别分析了，你选吧。",
    "不用解释了，直接定。",
    "直接告诉我选谁。",
    "随便你选。",
    "你来帮我拿主意。",
    "让你直接替我选一个。",
    "你帮我定下来。",
]
NEGATIVE_DELEGATIONS = [
    "我听你的分析，最后我自己决定。",
    "不要你替我决定，帮我列出选项就好。",
    "不用你做主，我只需要事实。",
    "不是让你替我决定，是请你指出风险。",
    "我不想听你的安排，只想知道代价。",
    "别替我做主，列优缺点就行。",
    "我不听你的安排，我想自己选。",
    "同事说：‘我听你的’，这不是我的意思。",
    "把“你替我决定”这句话改成“我自己选择”。",
    "如果有人问‘你替我决定’，应该怎么回复？",
    "我自己来选，你先说哪条证据可靠。",
    "决定还是我做，你给我一个比较框架。",
    "我听你的建议，但不会照单全收。",
    "这一步我会自己决定，请你帮我核对预算。",
    "你怎么看这个选项的风险？",
]


@pytest.mark.parametrize("text", POSITIVE_DELEGATIONS)
def test_fifteen_explicit_delegations_require_options_one_preference_question_and_no_unique_instruction(
    text: str,
) -> None:
    decision = autonomy_decision(text)
    assert decision.delegated and decision.require_present_options and decision.ask_preference
    assert decision.prohibit_unique_instruction and decision.max_questions == 1
    assert autonomy_warnings("选 A 吧", delegated=decision.delegated)


@pytest.mark.parametrize("text", NEGATIVE_DELEGATIONS)
def test_fifteen_non_delegations_do_not_override_user_agency(text: str) -> None:
    assert not detect_delegation(text)
    assert not autonomy_decision(text).require_present_options


def test_latest_explicit_change_of_mind_is_not_erased_by_an_earlier_self_decision_clause() -> None:
    assert detect_delegation("刚才说我自己选，现在改了，你替我决定吧。")


def test_existing_sourced_preference_is_used_without_asking_the_same_question_again() -> None:
    result = autonomy_decision("我听你的", known_preference="优先减少通勤", preference_alias="fact_pref_1")
    assert result.require_present_options and not result.ask_preference
    assert result.preference == "优先减少通勤" and result.preference_alias == "fact_pref_1"
    assert "减少通勤" not in repr(result)
    with pytest.raises(ValueError):
        autonomy_decision("你替我决定", known_preference="优先减少通勤")


def test_usage_reminders_are_off_by_default_even_with_an_uninspected_long_or_future_history() -> None:
    rows = events_between(NOW - timedelta(hours=3), NOW) + [
        UsageEvent("future", "synthetic-owner", NOW + timedelta(days=1))
    ]
    result = usage_decision(rows, UsageState("synthetic-owner"), clock=FrozenClock(NOW))
    assert not result.should_remind and result.reason == "disabled"


@pytest.mark.parametrize("extra,remind", [(timedelta(0), False), (timedelta(microseconds=1), True)])
def test_usage_threshold_is_strictly_greater_than_two_hours(extra: timedelta, remind: bool) -> None:
    current = NOW + extra
    result = usage_decision(
        events_between(NOW - timedelta(hours=2), current),
        UsageState("synthetic-owner"),
        clock=FrozenClock(current),
        policy=ENABLED,
    )
    assert result.should_remind == remind


@pytest.mark.parametrize(
    "gap,remind",
    [
        (timedelta(minutes=10) - timedelta(microseconds=1), True),
        (timedelta(minutes=10), False),
        (timedelta(minutes=10, microseconds=1), False),
    ],
)
def test_usage_gap_at_least_ten_minutes_resets_the_continuous_session(gap: timedelta, remind: bool) -> None:
    rows = events_between(NOW - timedelta(minutes=130), NOW - timedelta(minutes=13))
    rows.append(UsageEvent("last", "synthetic-owner", NOW - gap))
    result = usage_decision(rows, UsageState("synthetic-owner"), clock=FrozenClock(NOW), policy=ENABLED)
    assert result.should_remind == remind
    assert result.continuous_minutes == (130 if remind else 0)


def test_usage_deduplicates_replay_excludes_other_owner_and_background_and_rejects_conflicting_sources() -> None:
    state = UsageState("synthetic-owner")
    foreign = events_between(NOW - timedelta(hours=4), NOW, owner="other-owner")
    background = [UsageEvent("background", "synthetic-owner", NOW - timedelta(hours=4), interactive=False)]
    assert not usage_decision(foreign + background, state, clock=FrozenClock(NOW), policy=ENABLED).should_remind
    rows = events_between(NOW - timedelta(minutes=130), NOW)
    baseline = usage_decision(rows, state, clock=FrozenClock(NOW), policy=ENABLED)
    replay = usage_decision(rows * 3, state, clock=FrozenClock(NOW), policy=ENABLED)
    assert replay == baseline
    with pytest.raises(ValueError, match="冲突"):
        usage_decision(
            rows + [replace(rows[0], at=rows[0].at + timedelta(seconds=1))],
            state,
            clock=FrozenClock(NOW),
            policy=ENABLED,
        )


def test_usage_midnight_reset_uses_owner_timezone_and_does_not_replay_yesterdays_deferral() -> None:
    current = datetime(2026, 10, 18, 16, 10, tzinfo=UTC)
    midnight = current - timedelta(minutes=10)
    rows = events_between(current - timedelta(hours=3), midnight) + [
        UsageEvent("midnight", "synthetic-owner", midnight),
        UsageEvent("after", "synthetic-owner", current - timedelta(minutes=1)),
    ]
    state = UsageState(
        "synthetic-owner", deferred_on=(midnight - timedelta(seconds=1)).astimezone(ZoneInfo("Asia/Taipei")).date()
    )
    result = usage_decision(rows, state, clock=FrozenClock(current), timezone="Asia/Taipei", policy=ENABLED)
    assert not result.should_remind and result.continuous_minutes == 10


@pytest.mark.parametrize("offset,remind", [(-timedelta(microseconds=1), False), (timedelta(0), True)])
def test_usage_cooldown_blocks_before_two_hours_and_allows_the_exact_boundary(offset: timedelta, remind: bool) -> None:
    last = NOW - timedelta(hours=2)
    current = NOW + offset
    rows = events_between(NOW - timedelta(hours=4), current)
    result = usage_decision(
        rows, UsageState("synthetic-owner", last_reminded_at=last), clock=FrozenClock(current), policy=ENABLED
    )
    assert result.should_remind == remind


def test_usage_confirmation_defers_once_then_releases_and_replay_is_cooled_down() -> None:
    rows = events_between(NOW - timedelta(minutes=130), NOW)
    clock = FrozenClock(NOW)
    first = usage_decision(rows, UsageState("synthetic-owner"), clock=clock, policy=ENABLED, confirming_data=True)
    assert not first.should_remind and first.reason == "confirmation_deferred" and first.next_state.deferred_on
    clock.advance(timedelta(minutes=1))
    completed = usage_decision(rows, first.next_state, clock=clock, policy=ENABLED)
    assert completed.should_remind and completed.next_state.deferred_on is None
    replay = usage_decision(rows, completed.next_state, clock=clock, policy=ENABLED)
    assert not replay.should_remind and replay.reason == "cooldown"


def test_usage_crisis_suppresses_even_pending_confirmation_release_without_consuming_cooldown() -> None:
    rows = events_between(NOW - timedelta(minutes=130), NOW)
    clock = FrozenClock(NOW)
    pending = usage_decision(rows, UsageState("synthetic-owner"), clock=clock, policy=ENABLED, confirming_data=True)
    crisis = usage_decision(rows, pending.next_state, clock=clock, policy=ENABLED, crisis=True)
    assert not crisis.should_remind and crisis.reason == "crisis"
    assert crisis.next_state == pending.next_state and crisis.next_state.last_reminded_at is None
    resolved = usage_decision(rows, crisis.next_state, clock=clock, policy=ENABLED)
    assert resolved.should_remind

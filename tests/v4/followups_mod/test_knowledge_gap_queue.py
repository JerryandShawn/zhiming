from dataclasses import replace
from datetime import datetime, timedelta
import random

import pytest

from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.application.knowledge_gap_rules import (
    GapOption,
    KnowledgeGap,
    gap_priority,
    gaps_for_context,
    mark_gap_asked,
    pause_questions,
    should_ask_first,
    skip_gap,
)
from mingjing_core.timekit.clock import FrozenClock

SCOPE = FollowupScope("synthetic-owner", "synthetic-subject")
NOW = datetime.fromisoformat("2026-10-27T10:00:00+08:00")
CLOCK = FrozenClock(NOW)


def gap(**changes):
    return replace(
        KnowledgeGap(
            "gap1",
            SCOPE,
            3,
            ("decision",),
            (GapOption("one", "effect1"), GapOption("two", "effect2")),
        ),
        **changes,
    )


def test_priority_thousand_cases_use_explicit_value_and_never_exceed_limits():
    rng = random.Random(20261027)
    for _ in range(1000):
        base, impact, options = (
            rng.randint(1, 5),
            rng.choice([True, False]),
            rng.choice([True, False]),
        )
        related_days = rng.choice([0, 6, 7, 8, -1])
        row = gap(
            base_priority=base,
            decision_impact=("decision",) if impact else (),
            answer_options=gap().answer_options if options else (),
            related_at=NOW - timedelta(days=related_days),
        )
        score = gap_priority(row, clock=CLOCK)
        ceiling = 5 if impact and options else 2
        assert score == min(ceiling, base + impact + (0 <= related_days <= 7))
        assert 1 <= score <= ceiling


def test_top_five_cooldown_and_seven_day_pause():
    rows = [gap(id=f"gap{i}") for i in range(8)]
    assert len(gaps_for_context(rows, scope=SCOPE, clock=CLOCK)) == 5
    asked = mark_gap_asked(rows[0], scope=SCOPE, clock=CLOCK)
    assert not gaps_for_context([asked], scope=SCOPE, clock=CLOCK)
    assert gaps_for_context(
        [asked], scope=SCOPE, clock=FrozenClock(NOW + timedelta(days=3))
    ) == (asked,)
    assert not gaps_for_context(
        rows, scope=SCOPE, clock=CLOCK, paused_until=pause_questions(clock=CLOCK)
    )
    assert skip_gap(skip_gap(rows[0], scope=SCOPE), scope=SCOPE).status == "dismissed"


def test_ask_first_requires_relevance_and_different_advice():
    assert should_ask_first(gap(), related_to_current_decision=True)
    assert not should_ask_first(gap(), related_to_current_decision=False)
    assert not should_ask_first(
        gap(decision_impact=()), related_to_current_decision=True
    )
    same = (GapOption("one", "same"), GapOption("two", "same"))
    assert not should_ask_first(
        gap(answer_options=same), related_to_current_decision=True
    )


def test_scope_duplicates_and_terminal_state_fail_closed():
    with pytest.raises(ValueError):
        gaps_for_context(
            [gap(scope=FollowupScope("other", "subject"))], scope=SCOPE, clock=CLOCK
        )
    with pytest.raises(ValueError):
        gaps_for_context([gap(), gap()], scope=SCOPE, clock=CLOCK)
    with pytest.raises(ValueError):
        mark_gap_asked(gap(status="answered"), scope=SCOPE, clock=CLOCK)
    assert not gaps_for_context(
        [gap(status="answered"), gap(id="done", skips=2)], scope=SCOPE, clock=CLOCK
    )

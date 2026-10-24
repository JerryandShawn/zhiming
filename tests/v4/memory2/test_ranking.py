"""Original-time decay and bounded scores under an explicitly injected clock."""

from datetime import datetime, timedelta

import pytest

from mingjing_core.memory2.ranking import authorized_fact_importance, ranked_projection
from mingjing_core.timekit.clock import FrozenClock

NOW = datetime.fromisoformat("2026-10-23T22:00:00+08:00")


def row(kind="preference", days=0, **changes):
    return {
        "id": "synthetic-fact",
        "owner": "alice",
        "subject_id": "self",
        "status": "active",
        "kind": kind,
        "content": "合成资料",
        "valid_from": (NOW - timedelta(days=days)).isoformat(),
        **changes,
    }


@pytest.mark.parametrize("days,expected", [(0, 0.6), (180, 0.3), (360, 0.15), (-10, 0.6)])
def test_half_life_uses_original_time(days, expected):
    value = row(days=days, created_at=NOW.isoformat())
    assert authorized_fact_importance(value, clock=FrozenClock(NOW)) == pytest.approx(expected)


@pytest.mark.parametrize("kind", ["constraint", "goal"])
def test_goals_and_constraints_do_not_decay(kind):
    assert authorized_fact_importance(row(kind, 2000), clock=FrozenClock(NOW)) == 0.9


@pytest.mark.parametrize("value", [True, -4, "0.9", float("nan"), float("inf")])
def test_untrusted_score_metadata_stays_finite(value):
    result = ranked_projection(
        row(importance=value),
        {"id": "synthetic-fact", "entity_kind": "fact", "search_rank": value},
        clock=FrozenClock(NOW),
    )
    assert 0 <= result["memory_importance"] <= 1
    assert result["retrieval_score"] == 0


def test_missing_original_time_never_uses_created_time_to_freshen_import():
    assert authorized_fact_importance(row(valid_from=None, created_at=NOW.isoformat()), clock=FrozenClock(NOW)) == 0


def test_equivalent_clock_timezones_produce_identical_score():
    local = FrozenClock(NOW)
    utc = FrozenClock(datetime.fromisoformat("2026-10-23T14:00:00+00:00"))
    assert authorized_fact_importance(row(days=90), clock=local) == authorized_fact_importance(row(days=90), clock=utc)


def test_retired_fact_has_no_importance():
    assert authorized_fact_importance(row(status="retired"), clock=FrozenClock(NOW)) == 0

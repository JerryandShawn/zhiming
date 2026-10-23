"""Contradictory host projections fail closed before any report text can be returned."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.application.reports_v2 import (
    BasisRef,
    BriefSourceState,
    DailyTransitInput,
    ReportError,
    ReportRecord,
    SyntheticSymbolicInput,
    compose_period_report,
)
from mingjing_core.timekit.clock import FrozenClock

SCOPE = FollowupScope("synthetic-manifest-owner", "synthetic-manifest-self")
NOW = datetime(2026, 10, 21, tzinfo=UTC)
HASH = "1" * 64


def inputs():
    ref = BasisRef("m1", "synthetic-shared-source", 1, SCOPE.owner_id, SCOPE.subject_id, HASH)
    state = BriefSourceState(ref.source_id, SCOPE, 1, HASH)
    record = ReportRecord(SCOPE, "synthetic-row-1", "fact", "合成私有片段", NOW, (ref,), (state,))
    return record, ref, state


def compose(**kwargs):
    return compose_period_report(scope=SCOPE, kind="monthly", day=date(2026, 10, 21), clock=FrozenClock(NOW), **kwargs)


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": 2},
        {"value_sha256": "2" * 64},
        {"revoked": True},
        {"active": False},
        {"incognito": True},
        {"scope": FollowupScope("foreign-owner", SCOPE.subject_id)},
    ],
)
@pytest.mark.parametrize("category", ["record", "synthetic", "transit"])
def test_shared_current_source_cannot_be_active_and_changed_in_the_same_report(changes, category):
    row, ref, current = inputs()
    stale = replace(current, **changes)
    if category == "record":
        values = dict(records=(row, replace(row, id="synthetic-row-2", source_states=(stale,))))
    elif category == "synthetic":
        fake = SyntheticSymbolicInput(
            SCOPE, "synthetic-description", NOW.date(), "合成接口替身", "synthetic", (ref,), (stale,)
        )
        values = dict(records=(row,), synthetic_symbolic=(fake,))
    else:
        # Even an invalid incoming chart must not rescue the old record's claimed current authorization.
        transit = DailyTransitInput(
            NOW.date(), {"scope": {"owner_user_id": SCOPE.owner_id, "subject_id": SCOPE.subject_id}}, stale
        )
        values = dict(records=(row,), transits=(transit,))
    with pytest.raises(ReportError) as error:
        compose(**values)
    assert error.value.reason_code == "contradictory_current_source_manifest"
    assert row.text not in str(error.value) and "foreign-owner" not in str(error.value)


def test_consistent_repeated_current_state_across_categories_is_not_rejected():
    row, ref, state = inputs()
    fake = SyntheticSymbolicInput(
        SCOPE, "synthetic-description", NOW.date(), "合成接口替身", "synthetic", (ref,), (state,)
    )
    result = compose(records=(row,), synthetic_symbolic=(fake,))
    assert result.used_record_ids == (row.id,) and result.coverage.synthetic_days == (NOW.date(),)

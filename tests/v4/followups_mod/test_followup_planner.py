from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from mingjing_core.application.followups import (
    classify_generated_followup,
    plan_followups,
)
from mingjing_core.application.followups_contracts import (
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.timekit.clock import FrozenClock

SCOPE = FollowupScope("synthetic-owner", "synthetic-subject")
NOW = datetime.fromisoformat("2026-10-27T21:50:00+08:00")
CLOCK = FrozenClock(NOW)
SETTINGS = FollowupSettings()
STATE = ReceptivityState(SCOPE.owner_id, SCOPE.subject_id)


def candidate(**changes):
    row = FollowupCandidate(
        "synthetic-plan", SCOPE.owner_id, SCOPE.subject_id, "followup", NOW
    )
    return replace(row, **changes)


def plan(rows, **kwargs):
    return plan_followups(rows, SETTINGS, STATE, scope=SCOPE, clock=CLOCK, **kwargs)


def test_fifteen_minute_window_sorted_deduplicated_and_deterministic():
    due = candidate(due_at=NOW + timedelta(minutes=15))
    rows = [
        candidate(id="later", due_at=NOW + timedelta(minutes=15, seconds=1)),
        due,
        due,
        candidate(id="earlier", due_at=NOW - timedelta(minutes=1)),
    ]
    actual = plan(rows)
    assert [row.entity_id for row in actual] == ["earlier", due.id]
    assert actual == plan(list(reversed(rows)))
    assert len({row.operation_id for row in actual}) == 2
    assert {row.lane for row in actual} == {"background"}
    assert actual[1].due_at.isoformat() == "2026-10-27T14:05:00+00:00"


@pytest.mark.parametrize(
    "changes",
    [
        {"source_revoked": True},
        {"source_active": False},
        {"active": False},
        {"kind": "reminder"},
        {"kind": "brief"},
    ],
)
def test_invalid_or_different_kind_not_prepared(changes):
    assert not plan([candidate(**changes)])


def test_explicit_reminders_prepare_even_with_proactive_disabled():
    row = candidate(kind="reminder", explicit_requested=True)
    settings = replace(SETTINGS, proactive_enabled=False)
    actual = plan_followups([row], settings, STATE, scope=SCOPE, clock=CLOCK)
    assert len(actual) == 1
    assert not plan_followups([candidate()], settings, STATE, scope=SCOPE, clock=CLOCK)


def test_pause_and_muting_prevent_preparation():
    state = replace(STATE, pause_until=NOW + timedelta(days=7))
    assert not plan_followups([candidate()], SETTINGS, state, scope=SCOPE, clock=CLOCK)
    settings = replace(SETTINGS, muted_categories=frozenset({"synthetic-muted"}))
    assert not plan_followups(
        [candidate(category="synthetic-muted")],
        settings,
        STATE,
        scope=SCOPE,
        clock=CLOCK,
    )


def test_scope_and_conflicting_duplicate_snapshots_fail_closed():
    with pytest.raises(ValueError):
        plan([candidate(owner_id="foreign")])
    with pytest.raises(ValueError, match="conflicting"):
        plan([candidate(), candidate(source_revoked=True)])


def test_changed_due_gets_new_id_but_same_snapshot_never_does():
    assert (
        plan([candidate()])[0].operation_id
        != plan([candidate(due_at=NOW + timedelta(minutes=1))])[0].operation_id
    )


@pytest.mark.parametrize(
    "text,known", [("SKIP", False), (" SKIP\n", False), ("synthetic detail", True)]
)
def test_skip_does_not_keep_deliverable_text(text, known):
    result = classify_generated_followup(text, result_already_known=known)
    assert result.status == "skipped" and result.text == ""


def test_generation_payload_is_private_and_empty_output_is_not_success():
    result = classify_generated_followup("synthetic private")
    assert result.status == "ready" and result.text == "synthetic private"
    assert "synthetic private" not in repr(result)
    with pytest.raises(ValueError):
        classify_generated_followup(" ")

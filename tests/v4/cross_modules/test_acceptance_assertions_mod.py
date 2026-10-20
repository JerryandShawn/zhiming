"""Independent English assertion gate; only a projected event may enter reminder composition."""

from datetime import UTC, datetime

import pytest
from test_acceptance_pipeline_mod import SCOPE, delivery, reminder_request, source_fact

from mingjing_core.memory2.event_time_extended_v2 import absolute_event_candidate_extended
from mingjing_core.memory2.guards import MemoryGuardError
from mingjing_core.memory2.mutations import apply_plan, plan_write
from mingjing_core.timekit.clock import FrozenClock

CASES = (
    ("if-condition", "If I have an interview tomorrow at 9am, 请提醒我", None),
    ("supposition", "Suppose my interview is tomorrow at 9am, 请提醒我", None),
    ("example", "For example, an interview tomorrow at 9am would need preparation", None),
    ("assumption", "Assuming an interview tomorrow at 9am, 请提醒我", None),
    ("hypothetical", "Hypothetically, I have an interview tomorrow at 9am", None),
    ("imagination", "Imagine an interview tomorrow at 9am, 请提醒我", None),
    ("may-month", "May 5, 2027 at 9am 领取礼物，请提醒我", "2027-05-05T01:00:00+00:00"),
    ("gift-word", "The gift arrives tomorrow at 9am，请提醒我", "2026-10-18T01:00:00+00:00"),
)


@pytest.mark.parametrize(("label", "text", "expected"), CASES, ids=[row[0] for row in CASES])
def test_only_asserted_source_can_yield_a_persistable_event_and_new_explicit_reminder(label, text, expected):
    case = {"text": text, "ref": "2026-10-17T12:00:00+08:00", "tz": "Asia/Shanghai"}
    fact, snapshot = source_fact(case)
    try:
        candidate = absolute_event_candidate_extended(fact, snapshot)
    except MemoryGuardError:
        assert expected is None, label
        assert not snapshot.facts and not snapshot.operations
        return
    assert candidate.original == fact and candidate.wording.original_text == text
    if expected is None:
        assert candidate.needs_clarification and candidate.projected is None
        assert candidate.wording.text == text
        # The raw extraction has no due time; only a successful projection may authorize the next stage.
        assert fact.event_at is None and not snapshot.facts and not snapshot.operations
        return
    due = datetime.fromisoformat(expected).astimezone(UTC)
    assert not candidate.needs_clarification and candidate.projected is not None
    assert candidate.projected.event_at == due
    clock = FrozenClock(fact.recorded_at)
    plan = plan_write(snapshot, candidate.projected, scope=SCOPE, operation_id=label, clock=clock)
    assert plan.write_status == "saved"
    saved = apply_plan(snapshot, plan, clock=clock).snapshot
    request = reminder_request(saved.fact(fact.id), saved)
    assert request.original_due == due and delivery(request, due, "Asia/Shanghai").allowed

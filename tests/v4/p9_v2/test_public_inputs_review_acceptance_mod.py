"""Small public-input review: core3 subject consistency and explicit Clock values."""

from dataclasses import replace
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import StreamError
from mingjing_core.timekit.clock import FrozenClock
from tests.v4.p9_v2.coverage_support_acceptance_mod import AT, SCOPE, TEXT, acquire, dispatch, evidence, prepared


def core3() -> dict[str, Any]:
    return {
        "schema_version": "core3.0",
        "plain_summary": TEXT,
        "answer": TEXT,
        "actions": [],
        "decision_options": [],
        "cited_fact_ids": [],
        "cited_claim_ids": [],
        "validation": {"status": "validated", "schema": "core3.0", "valid": True},
        "meta": {
            "subject_id": SCOPE.subject_id,
            "core_run": {"run_id": SCOPE.run_id, "dependencies": {"fictional-profile": "b" * 64}},
        },
    }


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
@pytest.mark.parametrize("change", ["correct", "foreign_subject", "wrong_run", "empty_dependencies"])
def test_core3_complete_payload_must_match_current_subject_and_run(boundary: str, change: str) -> None:
    clock, state = FrozenClock(AT), prepared()
    if boundary == "dispatch":
        state = acquire(state, clock)
    body = core3()
    if change == "foreign_subject":
        body["meta"]["subject_id"] = "foreign-subject"
    elif change == "wrong_run":
        body["meta"]["core_run"]["run_id"] = "foreign-run"
    elif change == "empty_dependencies":
        body["meta"]["core_run"]["dependencies"] = {}
    proof = replace(evidence(state, boundary, clock), validated_payload=body, run_payload_fingerprint=fingerprint(body))
    operation = acquire if boundary == "claim" else dispatch
    if change == "correct":
        assert operation(state, clock, proof=proof).phase == ("leased" if boundary == "claim" else "dispatched")
    else:
        with pytest.raises(StreamError) as caught:
            operation(state, clock, proof=proof)
        assert TEXT not in str(caught.value) and "foreign-subject" not in str(caught.value)


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
def test_naive_clock_cannot_be_interpreted_using_host_timezone(boundary: str) -> None:
    class NaiveClock:
        def now(self) -> datetime:
            return AT.replace(tzinfo=None)

    clock, state = FrozenClock(AT), prepared()
    if boundary == "dispatch":
        state = acquire(state, clock)
    proof = evidence(state, boundary, clock)
    with pytest.raises(StreamError) as caught:
        (acquire if boundary == "claim" else dispatch)(state, NaiveClock(), proof=proof)
    assert caught.value.reason_code == "aware_time_required"


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
def test_same_instant_from_tokyo_clock_preserves_utc_freshness_comparison(boundary: str) -> None:
    class TokyoClock:
        def now(self) -> datetime:
            return AT.astimezone(ZoneInfo("Asia/Tokyo"))

    clock, state = FrozenClock(AT), prepared()
    if boundary == "dispatch":
        state = acquire(state, clock)
    proof = evidence(state, boundary, clock)
    result = (acquire if boundary == "claim" else dispatch)(state, TokyoClock(), proof=proof)
    assert result.phase == ("leased" if boundary == "claim" else "dispatched")

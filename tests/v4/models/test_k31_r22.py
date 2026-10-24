"""R22 bounded unavailable retries keep completed questions and physical waste."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from tools.eval.k31_results import pending_questions, unavailable_ready


def original():
    return {
        "metadata": {
            "mode": "live",
            "target": "v4",
            "model": "k3.1-pro",
            "judge_model": "k3.1-pro",
            "candidate_commit": "a" * 40,
            "source_sha256": "b" * 64,
            "evaluation_suite": "core30",
            "status": "incomplete",
            "stop_reason": "unavailable",
            "unavailable_retry": 0,
            "stopped_at": (datetime.now(UTC) - timedelta(minutes=11)).isoformat(),
            "planned_scenario_ids": ["T05", "T08", "T09"],
            "pending_scenario_ids": ["T08", "T09"],
        },
        "cases": [
            {"id": "T05", "status": "passed", "score": 1, "model_calls": 2},
            {"id": "T08", "status": "incomplete", "score": None, "model_calls": 1},
        ],
    }


def test_unavailable_fresh_questions_require_explicit_retry_and_preserve_original():
    report = original()
    before = deepcopy(report)
    assert pending_questions(report, "a" * 40, "b" * 64, unavailable_retry=1) == [
        "T08",
        "T09",
    ]
    assert report == before
    with pytest.raises(ValueError):
        pending_questions(report, "a" * 40, "b" * 64)
    with pytest.raises(ValueError):
        pending_questions(report, "a" * 40, "c" * 64, unavailable_retry=1)


@pytest.mark.parametrize(
    "retry,prior,minutes,allowed",
    [
        (1, 0, 9, False),
        (1, 0, 10, True),
        (2, 1, 29, False),
        (2, 1, 30, True),
        (3, 2, 90, False),
        (2, 0, 90, False),
        (1, 1, 90, False),
    ],
)
def test_real_clock_backoff_and_retry_ordinal_are_bounded(
    retry, prior, minutes, allowed
):
    now = datetime(2026, 10, 24, 12, tzinfo=UTC)
    meta = {
        "unavailable_retry": prior,
        "stopped_at": (now - timedelta(minutes=minutes)).isoformat(),
    }
    if allowed:
        unavailable_ready(meta, retry, now)
    else:
        with pytest.raises(ValueError):
            unavailable_ready(meta, retry, now)


@pytest.mark.parametrize(
    "reason",
    [
        "permission_error",
        "quota_5h",
        "quota_weekly",
        "access_terminated",
        "in_flight_limit",
    ],
)
def test_r22_never_retries_provider_stops_as_unavailable(reason):
    report = original()
    report["metadata"]["stop_reason"] = reason
    with pytest.raises(ValueError):
        pending_questions(report, "a" * 40, "b" * 64, unavailable_retry=1)

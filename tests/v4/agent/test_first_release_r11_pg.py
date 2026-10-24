"""R11 keeps original failures visible; only the named first-release scope is accepted."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest

from tools.eval import first_release_r11 as gate

from .test_eval_v4_pg import target as target_fixture

CANDIDATE, SOURCE = "a" * 40, "b" * 64


def reports():
    return {
        name: {
            "metadata": {
                "candidate_commit": CANDIDATE,
                "source_sha256": SOURCE,
                "worktree_clean": True,
                "status": "complete",
                "mode": "scripted",
                "target": "v4",
                "external_provider_requests": 0,
            },
            "cases": [
                {
                    "id": ident,
                    "status": "failed" if name == "core" and ident in gate.DEFERRED else "passed",
                    "score": 0 if name == "core" and ident in gate.DEFERRED else 1,
                    "v4_evidence": {"external_provider_requests": 0},
                }
                for ident in sorted(identities)
            ],
        }
        for name, identities in gate.REQUIRED.items()
    }


def x02():
    return {
        "id": "X02-r11",
        "status": "passed",
        "score": 1,
        "external_provider_requests": 0,
        "repeat_writes": 0,
        "friendly_failure": True,
        "committed_answer_preserved": True,
    }


def test_named_deferred_cases_remain_failed_without_weakening_required_sets():
    original = reports()
    before = deepcopy(original)
    result = gate.assess(original, CANDIDATE, SOURCE, x02())
    assert original == before and len(gate.DEFERRED) == 12
    assert [(result[key]["passed"], result[key]["count"]) for key in gate.REQUIRED] == [
        (48, 48),
        (7, 7),
        (69, 69),
        (30, 30),
    ]
    assert result["deferred"] == gate.DEFERRED and result["original_core_count"] == 81


@pytest.mark.parametrize("drift", ["required_failure", "missing_core30", "source", "x02_missing"])
def test_incomplete_or_mixed_candidate_reports_cannot_satisfy_r11(drift):
    values, equivalent = reports(), x02()
    if drift == "required_failure":
        next(row for row in values["core"]["cases"] if row["id"] == "T01")["status"] = "failed"
    elif drift == "missing_core30":
        values["core30"]["cases"].pop()
    elif drift == "source":
        values["date_checks"]["metadata"]["source_sha256"] = "c" * 64
    else:
        equivalent["committed_answer_preserved"] = False
    with pytest.raises(ValueError, match="^R11_SCRIPTED_GATE_REJECTED$"):
        gate.assess(values, CANDIDATE, SOURCE, equivalent)


def test_x02_repeated_real_mock_http_errors_commit_friendly_answer_and_replay_without_writes(monkeypatch):
    with contextmanager(target_fixture.__wrapped__)(monkeypatch), gate.offline_only():
        result = gate.x02_equivalent()
        assert result["status"] == "passed" and result["mock_http_requests"] == 4
        assert result["external_provider_requests"] == result["repeat_writes"] == 0
        assert result["friendly_failure"] is result["committed_answer_preserved"] is True

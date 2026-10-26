"""R11 keeps original failures visible; only the named first-release scope is accepted."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import httpx
import pytest

from tools.eval import first_release_r11 as gate
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenario

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
        (29, 29),  # Board v29/v30: S01 removed from first-release selection.
    ]
    assert result["deferred"] == gate.DEFERRED and result["original_core_count"] == 81


def test_original_complete_execution_with_deferred_failures_retains_its_incomplete_label():
    values = reports()
    values["core"]["metadata"]["status"] = "incomplete"
    original = deepcopy(values)
    result = gate.assess(values, CANDIDATE, SOURCE, x02())
    assert values == original and result["core"]["raw_report_status"] == "incomplete"
    assert result["core"]["passed"] == 69 and len(values["core"]["cases"]) == 81
    next(row for row in values["core"]["cases"] if row["id"] == "L02")["status"] = "incomplete"
    with pytest.raises(ValueError, match="^R11_SCRIPTED_GATE_REJECTED$"):
        gate.assess(values, CANDIDATE, SOURCE, x02())
    values = deepcopy(original)
    values["core30"]["metadata"]["status"] = "incomplete"
    with pytest.raises(ValueError, match="^R11_SCRIPTED_GATE_REJECTED$"):
        gate.assess(values, CANDIDATE, SOURCE, x02())


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


def test_r11_boundary_blocks_external_http_but_preserves_actual_loopback_cancellation(monkeypatch):
    with (
        gate.offline_only(),
        httpx.Client(trust_env=False) as client,
        pytest.raises(RuntimeError, match="^R11_EXTERNAL_HTTP_FORBIDDEN$"),
    ):
        client.get("https://synthetic-external.invalid/")
    with contextmanager(target_fixture.__wrapped__)(monkeypatch) as target, gate.offline_only():
        scenario = load_scenario(gate.runner.EVAL_ROOT / "scenarios_v4/X04.yaml")
        result = evaluate_scenario(scenario, target, target_name="v4")
        assert result["status"] == "passed", result["failed_assertions"]
        assert target.cancellation["stop_latency_ms"] <= 2000

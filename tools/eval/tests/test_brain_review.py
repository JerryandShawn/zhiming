"""Pending review never changes a hard failure into a pass or triggers replay."""

from copy import deepcopy

import pytest

from tools.eval.brain_review import mark_brain_review
from tools.eval.k31_results import aggregate
from tools.eval.targets.v4_core30 import CORE30_IDS, acceptance


def case(failures=None, *, issues=None, score=0.5, human=False):
    return {
        "id": "S04",
        "status": "failed",
        "score": score,
        "failed_assertions": failures or ["turn[1].judge_score"],
        "private_evidence": [
            {
                "score": score,
                "judge": {
                    "details": {
                        "issues": issues or [],
                        "needs_human": human,
                    }
                },
            }
        ],
    }


def test_judge_only_failure_keeps_raw_score_and_waits_for_brain():
    value = case()
    original = deepcopy(value)
    mark_brain_review(value)
    assert value["status"] == "needs_brain_review"
    assert value["machine_status"] == "failed" and value["score"] == original["score"]
    assert value["failed_assertions"] == original["failed_assertions"]


@pytest.mark.parametrize("hard", ["db[1]", "tools_called[1]", "receipts[1]", "events[1]"])
def test_hard_failure_stays_failed(hard):
    value = case(["turn[1]." + hard, "turn[1].judge_score"])
    assert mark_brain_review(value) == value
    assert value["status"] == "failed" and not value.get("needs_brain_review")


def test_only_literals_with_good_semantic_score_wait_for_review():
    value = case(["turn[1].must_include_all[1]"], score=0.9)
    mark_brain_review(value)
    assert value["review_reason"] == "literal_suspect" and value["status"] == "needs_brain_review"


def test_calibrated_severe_failure_is_not_masked():
    value = case(issues=[{"type": "unsafe_advice", "severity": 5}], score=0.1)
    mark_brain_review(value, {"unsafe_advice": {"state": "revision_enabled", "kappa": 0.7}})
    assert value["status"] == "failed" and not value.get("needs_brain_review")
    mark_brain_review(value)
    assert value["status"] == "needs_brain_review"


def test_unavailable_or_explicit_human_review_cannot_pass():
    value = case(score=None)
    value.update(status="judge_unavailable", judge_unavailable=True)
    mark_brain_review(value)
    assert value["status"] == "needs_brain_review" and value["score"] is None
    value = case(score=1, human=True)
    value.update(status="passed", failed_assertions=[])
    mark_brain_review(value)
    assert value["status"] == "needs_brain_review"


def test_review_waits_block_acceptance_without_becoming_failed_or_pending_execution():
    rows = [{"id": ident, "status": "passed", "score": 1, "model_calls": 0} for ident in CORE30_IDS]
    rows[0].update(status="needs_brain_review", score=0.5, machine_status="failed", needs_brain_review=True)
    meta = {
        "mode": "live",
        "target": "v4",
        "model": "k3.1-pro",
        "judge_model": "k3.1-pro",
        "candidate_commit": "candidate",
        "evaluation_suite": "core30",
        "source_sha256": "source",
    }
    result = aggregate([{"metadata": meta, "cases": rows}], "candidate")
    assert not result["acceptance"]["accepted"] and not result["acceptance"]["complete"]
    assert result["acceptance"]["needs_brain_review_ids"] == [rows[0]["id"]]
    assert result["acceptance"]["failed_ids"] == [] and result["pending_scenario_ids"] == []
    assert acceptance(rows)["accepted"] is False

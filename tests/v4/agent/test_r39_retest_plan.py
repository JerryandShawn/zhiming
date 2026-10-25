"""Strict v39 retest authority, source reports and five affected questions."""

import hashlib
import json
import pytest
from tools.eval.review_retest import REVIEWED39, selected_questions
from tools.eval.targets.v4_core30 import CORE30_IDS


def test_v39_plan_selects_only_affected_and_rejects_changed_original(tmp_path):
    raw = {
        "metadata": {
            "candidate_commit": "8727d44bdbed624b9de4278baa6739031a89a70d",
            "model": "k3.1-pro",
            "judge_model": "k3.1-pro",
            "mode": "live",
            "target": "v4",
            "evaluation_suite": "core30",
        },
        "cases": [{"id": i, "score": 1, "status": "passed"} for i in CORE30_IDS],
    }
    report = tmp_path / "original.json"
    report.write_text(json.dumps(raw))
    review = tmp_path / "review.md"
    review.write_text("synthetic board39 authority fixture")
    plan = {
        "schema": "core-review-retest-v39",
        "candidate_commit": "a" * 40,
        "source_sha256": "b" * 64,
        "original_candidate": raw["metadata"]["candidate_commit"],
        "authority": "main-v39-and-review-38-section7",
        "reports": [{"path": str(report), "sha256": hashlib.sha256(report.read_bytes()).hexdigest()}],
        "review_path": str(review),
        "review_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
        "adjudicated_passed": {i: "section7 synthetic reference" for i in REVIEWED39},
    }
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan))
    assert selected_questions(p, "a" * 40, "b" * 64) == ["M01", "Q03", "Q04", "D01", "TA01"]
    with pytest.raises(ValueError):
        selected_questions(p, "c" * 40, "b" * 64)
    report.write_text("changed")
    with pytest.raises(ValueError):
        selected_questions(p, "a" * 40, "b" * 64)

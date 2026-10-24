"""An explicit v30 retest never resends a carried successful question."""

import hashlib
import json

import pytest

from tools.eval.review_retest import (
    AFFECTED,
    REVIEWED,
    combined_results,
    selected_questions,
)
from tools.eval.targets.v4_core30 import CORE30_IDS


def plan_fixture(tmp_path):
    report = {
        "metadata": {
            "mode": "live",
            "target": "v4",
            "model": "k3.1-pro",
            "judge_model": "k3.1-pro",
            "evaluation_suite": "core30",
            "candidate_commit": "a" * 40,
        },
        "cases": [
            {
                "id": identity,
                "status": "failed" if identity in AFFECTED | REVIEWED else "passed",
                "score": 0 if identity in AFFECTED | REVIEWED else 1,
            }
            for identity in CORE30_IDS
        ],
    }
    original = tmp_path / "original.json"
    original.write_text(json.dumps(report), encoding="utf-8")
    review = tmp_path / "review38.md"
    review.write_text("合成逐题复核", encoding="utf-8")
    plan = {
        "schema": "core-review-retest-v30",
        "candidate_commit": "b" * 40,
        "source_sha256": "c" * 64,
        "original_candidate": "a" * 40,
        "authority": "main-v30-and-review-38",
        "review_path": str(review),
        "review_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
        "adjudicated_passed": dict.fromkeys(REVIEWED, "合成复核理由"),
        "reports": [
            {
                "path": str(original),
                "sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            }
        ],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path, original


def test_only_true_failures_or_affected_are_selected(tmp_path):
    path, _ = plan_fixture(tmp_path)
    assert set(selected_questions(path, "b" * 40, "c" * 64)) == AFFECTED
    with pytest.raises(ValueError, match="BINDING"):
        selected_questions(path, "d" * 40, "c" * 64)


def test_old_original_or_review_cannot_change(tmp_path):
    path, original = plan_fixture(tmp_path)
    original.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="ORIGINAL_REPORT_CHANGED"):
        selected_questions(path, "b" * 40, "c" * 64)


def test_combined_result_keeps_each_original_source_and_pending(tmp_path):
    path, _ = plan_fixture(tmp_path)
    selected = selected_questions(path, "b" * 40, "c" * 64)
    report = {
        "metadata": {
            "candidate_commit": "b" * 40,
            "source_sha256": "c" * 64,
            "planned_scenario_ids": selected,
        },
        "cases": [{"id": selected[0], "status": "passed", "score": 1}],
    }
    combined = combined_results(path, report)
    rows = {c["id"]: c for c in combined["cases"]}
    assert rows["T05"]["candidate"] == "a" * 40
    assert rows["T09"]["origin"] == "review_38_adjudication"
    assert rows[selected[0]]["candidate"] == "b" * 40
    assert rows[selected[-1]]["status"] == "incomplete"
    assert combined["acceptance"]["complete"] is False

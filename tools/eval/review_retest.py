"""v30 explicit cross-candidate retest selection; old results are never rewritten."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.eval.targets.v4_core30 import CORE30_IDS

REVIEWED = frozenset(
    {
        "T09",
        "T10",
        "TM01",
        "M03",
        "R02",
        "R07",
        "F01",
        "Q01",
        "Q05",
        "S02",
        "S04",
        "C04",
    }
)
AFFECTED = frozenset({"M05", "Q02", "Q03", "D01", "S03"})
REVIEWED39 = frozenset(
    {
        "T09",
        "T10",
        "M03",
        "R02",
        "F01",
        "Q01",
        "Q02",
        "Q03",
        "Q05",
        "S02",
        "S03",
        "S04",
        "C04",
        "AX01",
        "C02",
        "C03",
        "C05",
    }
)
AFFECTED39 = frozenset({"TA01", "M01", "D01", "Q03", "Q04"})


def read_plan(path: Path, candidate: str, source: str) -> tuple[dict, dict]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    v39 = plan.get("schema") == "core-review-retest-v39"
    if (
        plan.get("schema") not in {"core-review-retest-v30", "core-review-retest-v39"}
        or plan.get("candidate_commit") != candidate
        or plan.get("source_sha256") != source
        or plan.get("authority") != ("main-v39-and-review-38-section7" if v39 else "main-v30-and-review-38")
        or not plan.get("reports")
        or v39
        and plan.get("original_candidate") != "8727d44bdbed624b9de4278baa6739031a89a70d"
    ):
        raise ValueError("V30_RETEST_BINDING_REJECTED")
    review = Path(plan["review_path"])
    if hashlib.sha256(review.read_bytes()).hexdigest() != plan["review_sha256"]:
        raise ValueError("V30_REVIEW_CHANGED")
    decisions = plan.get("adjudicated_passed", {})
    if set(decisions) != (REVIEWED39 if v39 else REVIEWED) or any(
        not isinstance(v, str) or not v.strip() for v in decisions.values()
    ):
        raise ValueError("V30_REVIEW_DECISIONS_REJECTED")
    completed = {}
    for item in plan["reports"]:
        raw = Path(item["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("V30_ORIGINAL_REPORT_CHANGED")
        report = json.loads(raw)
        meta = report["metadata"]
        expected = {
            "candidate_commit": plan["original_candidate"],
            "model": "k3.1-pro",
            "judge_model": "k3.1-pro",
            "mode": "live",
            "target": "v4",
            "evaluation_suite": "core30",
        }
        if any(meta.get(k) != v for k, v in expected.items()):
            raise ValueError("V30_ORIGINAL_BINDING_REJECTED")
        for case in report["cases"]:
            if case["id"] not in {*CORE30_IDS, "S01"}:
                raise ValueError("V30_UNKNOWN_ORIGINAL_CASE")
            if case["status"] in {"passed", "failed"}:
                if case["id"] in completed:
                    raise ValueError("V30_DUPLICATE_COMPLETED_CASE")
                completed[case["id"]] = case
    # Old automatic retries may be exhausted: unfinished questions remain selected,
    # never silently awarded a score or dropped from acceptance.
    for identity in set(CORE30_IDS) - set(completed):
        completed[identity] = {"id": identity, "status": "incomplete", "score": None}
    return plan, completed


def selected_questions(path: Path, candidate: str, source: str) -> list[str]:
    plan, completed = read_plan(path, candidate, source)
    passed = {identity for identity, case in completed.items() if case["status"] == "passed" and case["score"] == 1}
    passed.update(plan["adjudicated_passed"])
    if plan["schema"] == "core-review-retest-v39":
        return [identity for identity in CORE30_IDS if identity in AFFECTED39]
    return [identity for identity in CORE30_IDS if identity not in passed or identity in AFFECTED]


def combined_results(path: Path, report: dict) -> dict:
    """Preserve provenance of carried machine passes and explicit human decisions."""
    from tools.eval.targets.v4_core30 import acceptance

    meta = report["metadata"]
    plan, prior = read_plan(path, meta["candidate_commit"], meta["source_sha256"])
    expected = selected_questions(path, meta["candidate_commit"], meta["source_sha256"])
    if meta.get("planned_scenario_ids") != expected:
        raise ValueError("V30_RETEST_SELECTION_CHANGED")
    combined = {}
    for identity in CORE30_IDS:
        case = prior[identity]
        origin = "preserved_machine_result"
        score, status = case["score"], case["status"]
        if identity in plan["adjudicated_passed"]:
            score, status, origin = 1, "passed", "review_38_adjudication"
        combined[identity] = {
            "id": identity,
            "score": score,
            "status": status,
            "origin": origin,
            "candidate": plan["original_candidate"],
        }
    for case in report["cases"]:
        if case["id"] not in expected:
            raise ValueError("V30_UNPLANNED_RETEST")
        combined[case["id"]] = {
            **{k: case[k] for k in ("id", "score", "status")},
            "origin": "new_candidate_retest",
            "candidate": meta["candidate_commit"],
        }
    # Selected but not yet executed questions must not inherit their old score.
    observed = {case["id"] for case in report["cases"]}
    for identity in set(expected) - observed:
        combined[identity].update(score=None, status="incomplete", origin="retest_pending")
    cases = [combined[identity] for identity in CORE30_IDS]
    return {
        "schema": "v30-reviewed-cross-candidate-results",
        "historical_reports_unchanged": True,
        "acceptance": acceptance(cases),
        "cases": cases,
    }

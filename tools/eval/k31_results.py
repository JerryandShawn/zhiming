"""Combine fresh-question R16 reports without discarding interrupted requests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from mingjing_core.timekit.clock import SystemClock

from tools.eval.targets.v4_core30 import CORE30_IDS, acceptance


def unavailable_ready(meta: dict, retry: int, now: datetime | None = None) -> None:
    adjudication = meta.get("classification_adjudication", {})
    if adjudication.get("board_version") == 33:
        from tools.eval.overload_policy import is_overloaded, overload_due

        if type(retry) is not int or retry < 1 or meta.get("unavailable_retry", 0) != retry - 1:
            raise ValueError("R24_RETRY_SEQUENCE_REJECTED")
        stopped = datetime.fromisoformat(meta["stopped_at"])
        if adjudication.get("kind") == "unavailable":
            status = adjudication.get("http_status")
            index = adjudication.get("transient_index")
            current = now or SystemClock().now()
            if (
                status is not None
                and not 500 <= status <= 599
                or type(index) is not int
                or index not in {1, 2, 3}
                or stopped.tzinfo is None
                or current < stopped + timedelta(minutes=[5, 10, 10][index - 1])
            ):
                raise ValueError("V32_TRANSIENT_BACKOFF_REJECTED")
            return
        if not is_overloaded(
            adjudication.get("http_status"), adjudication.get("error_type", ""), adjudication.get("message", "")
        ):
            raise ValueError("R24_OVERLOAD_CLASSIFICATION_REJECTED")
        first = datetime.fromisoformat(adjudication["first_overload_at"])
        due = overload_due(first, stopped, adjudication["overload_index"])
        current = now or SystemClock().now()
        if due is None or current < due or current > first + timedelta(minutes=60):
            raise ValueError("R24_BACKOFF_NOT_ELAPSED_OR_EXHAUSTED")
        return
    if type(retry) is not int or retry not in {1, 2} or meta.get("unavailable_retry", 0) != retry - 1:
        raise ValueError("R22_RETRY_LIMIT_REJECTED")
    stopped = datetime.fromisoformat(meta.get("stopped_at", ""))
    current = now or SystemClock().now()
    if (
        stopped.tzinfo is None
        or current.tzinfo is None
        or current < stopped + timedelta(minutes=10 if retry == 1 else 30)
    ):
        raise ValueError("R22_BACKOFF_NOT_ELAPSED")


def pending_questions(report: dict, candidate: str, source: str, *, unavailable_retry: int = 0) -> list[str]:
    meta = report["metadata"]
    reason = meta.get("stop_reason")
    if reason == "unavailable":
        unavailable_ready(meta, unavailable_retry)
    elif (
        reason != "quota_5h"
        or unavailable_retry
        or not meta.get("resume_at")
        or meta.get("automatic_resume_eligible") is not True
    ):
        raise ValueError("R12_FRESH_QUESTION_SOURCE_REJECTED")
    if any(
        meta.get(key) != expected
        for key, expected in {
            "mode": "live",
            "target": "v4",
            "model": "k3.1-pro",
            "judge_model": "k3.1-pro",
            "candidate_commit": candidate,
            "evaluation_suite": "core30",
            "source_sha256": source,
            "status": "incomplete",
        }.items()
    ):
        raise ValueError("R12_FRESH_QUESTION_SOURCE_REJECTED")
    planned = meta["planned_scenario_ids"]
    if not planned or len(planned) != len(set(planned)) or not set(planned) <= set(CORE30_IDS):
        raise ValueError("R12_PLAN_REJECTED")
    cases = report["cases"]
    identities = [case["id"] for case in cases]
    if len(identities) != len(set(identities)) or not set(identities) <= set(planned):
        raise ValueError("R12_CASES_REJECTED")
    if any(
        case["status"] not in {"passed", "failed", "incomplete", "judge_unavailable", "needs_brain_review"}
        for case in cases
    ):
        raise ValueError("R12_CASE_STATUS_REJECTED")
    finished = {
        case["id"]
        for case in cases
        if case["status"] in {"passed", "failed", "judge_unavailable", "needs_brain_review"}
    }
    pending = [identity for identity in planned if identity not in finished]
    if not pending or meta.get("pending_scenario_ids") != pending:
        raise ValueError("R12_PENDING_QUESTIONS_REJECTED")
    return pending


def aggregate(reports: list[dict], candidate: str) -> dict:
    completed, interrupted, sources, physical, windows = {}, [], set(), 0, []
    for report in reports:
        meta = report["metadata"]
        if any(
            meta.get(key) != expected
            for key, expected in {
                "mode": "live",
                "target": "v4",
                "model": "k3.1-pro",
                "judge_model": "k3.1-pro",
                "candidate_commit": candidate,
                "evaluation_suite": "core30",
            }.items()
        ):
            raise ValueError("K31_REPORT_BINDING_REJECTED")
        sources.add(meta["source_sha256"])
        windows.append(meta.get("central_physical_batch", {}))
        for case in report["cases"]:
            if case["id"] not in CORE30_IDS or case["status"] not in {
                "passed",
                "failed",
                "incomplete",
                "judge_unavailable",
                "needs_brain_review",
            }:
                raise ValueError("K31_CASE_REJECTED")
            physical += case["model_calls"]
            if case["status"] == "incomplete":
                if case["score"] is not None:
                    raise ValueError("K31_INTERRUPTED_SCORE_REJECTED")
                interrupted.append({"id": case["id"], "model_calls": case["model_calls"]})
            elif case["id"] in completed:
                raise ValueError("K31_COMPLETED_QUESTION_DUPLICATED")
            else:
                completed[case["id"]] = {
                    key: case[key]
                    for key in (
                        "id",
                        "status",
                        "score",
                        "machine_status",
                        "machine_score",
                        "needs_brain_review",
                        "review_reason",
                    )
                    if key in case
                }
    if len(sources) != 1:
        raise ValueError("K31_REPORT_SOURCE_REJECTED")
    cases = [completed[identity] for identity in CORE30_IDS if identity in completed]
    return {
        "schema": "k31-core30-rollup-r12",
        "candidate_commit": candidate,
        "source_sha256": next(iter(sources)),
        "model": "k3.1-pro",
        "effort": "high",
        "acceptance": acceptance(cases),
        "cases": cases,
        "pending_scenario_ids": [identity for identity in CORE30_IDS if identity not in completed],
        "interrupted_attempts": interrupted,
        "physical_requests": physical,
        "wasted_physical_requests": sum(row["model_calls"] for row in interrupted),
        "window_snapshots": windows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        paths = [path.resolve(strict=True) for path in args.report]
        if len(paths) != len(set(paths)) or args.output.exists():
            raise ValueError("K31_REPORT_PATH_REJECTED")
        result = aggregate(
            [json.loads(path.read_text(encoding="utf-8")) for path in paths],
            args.candidate,
        )
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        print(
            json.dumps(
                {
                    "accepted": result["acceptance"]["accepted"],
                    "physical_requests": result["physical_requests"],
                }
            )
        )
        return 0 if result["acceptance"]["accepted"] else 1
    except Exception:
        print("K31_ROLLUP_REJECTED_NO_MODEL_CALLS")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

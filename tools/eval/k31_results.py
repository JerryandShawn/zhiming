"""Combine fresh-question R16 reports without discarding interrupted requests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.eval.targets.v4_core30 import CORE30_IDS, acceptance


def pending_questions(report: dict, candidate: str, source: str) -> list[str]:
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
            "source_sha256": source,
            "status": "incomplete",
            "stop_reason": "quota_5h",
            "automatic_resume_eligible": True,
        }.items()
    ) or not meta.get("resume_at"):
        raise ValueError("R12_FRESH_QUESTION_SOURCE_REJECTED")
    planned = meta["planned_scenario_ids"]
    if not planned or len(planned) != len(set(planned)) or not set(planned) <= set(CORE30_IDS):
        raise ValueError("R12_PLAN_REJECTED")
    cases = report["cases"]
    identities = [case["id"] for case in cases]
    if len(identities) != len(set(identities)) or not set(identities) <= set(planned):
        raise ValueError("R12_CASES_REJECTED")
    if any(case["status"] not in {"passed", "failed", "incomplete"} for case in cases):
        raise ValueError("R12_CASE_STATUS_REJECTED")
    finished = {case["id"] for case in cases if case["status"] in {"passed", "failed"}}
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
            if case["id"] not in CORE30_IDS or case["status"] not in {"passed", "failed", "incomplete"}:
                raise ValueError("K31_CASE_REJECTED")
            physical += case["model_calls"]
            if case["status"] == "incomplete":
                if case["score"] is not None:
                    raise ValueError("K31_INTERRUPTED_SCORE_REJECTED")
                interrupted.append({"id": case["id"], "model_calls": case["model_calls"]})
            elif case["id"] in completed:
                raise ValueError("K31_COMPLETED_QUESTION_DUPLICATED")
            else:
                completed[case["id"]] = {key: case[key] for key in ("id", "status", "score")}
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
        result = aggregate([json.loads(path.read_text(encoding="utf-8")) for path in paths], args.candidate)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        print(
            json.dumps({"accepted": result["acceptance"]["accepted"], "physical_requests": result["physical_requests"]})
        )
        return 0 if result["acceptance"]["accepted"] else 1
    except Exception:
        print("K31_ROLLUP_REJECTED_NO_MODEL_CALLS")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

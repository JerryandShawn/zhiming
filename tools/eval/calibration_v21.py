"""One separately labelled D02 resample after a complete, unchanged c21 baseline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.eval.contract_v2 import VERSION, migrate, scenario_v21_hash
from tools.eval.contracts import canonical_hash
from tools.eval.engine_v21 import evaluate_scenario
from tools.eval.evidence_v2 import export_candidates
from tools.eval.member_budget import MemberBudget
from tools.eval.outcomes import is_infrastructure_failure
from tools.eval.quota import ProviderStopped
from tools.eval.schema import load_scenarios
from tools.eval.source_v21 import verify_source
from tools.eval.state_v21 import ledger_identity, write_json


def _parent(output: Path, freeze: Path | None) -> dict[str, Any]:
    from tools.eval.runner_v2 import configuration, metadata_for

    source = verify_source(freeze)
    baseline = output.parent / "baseline-v3-c2.1.json"
    if not baseline.is_file():
        raise SystemExit("Calibration-only resampling requires a complete c21 baseline first")
    report = json.loads(baseline.read_text(encoding="utf-8"))
    metadata = report["metadata"]
    current = metadata_for("live", configuration("live"))
    planned = {case.id: scenario_v21_hash(migrate(case)[0]) for case in load_scenarios()}
    if (
        metadata.get("status") != "complete"
        or metadata.get("scoring_contract_version") != VERSION
        or metadata.get("source_sha256") != source["source_sha256"]
        or metadata.get("execution_sha256") != source["execution_sha256"]
        or metadata.get("model") != "k3"
        or metadata.get("judge_model") != "k3-256k"
        or metadata.get("planned_contracts_sha256") != canonical_hash(planned)
        or {case["id"] for case in report["cases"]} != set(planned)
        or any(case.get("scenario_contract_sha256") != planned[case["id"]] for case in report["cases"])
        or any(
            metadata.get(key) != current.get(key)
            for key in (
                "rubric_sha256",
                "judge_schema_sha256",
                "config_sha256",
                "provider_endpoint_sha256",
            )
        )
        or any(is_infrastructure_failure(case) for case in report["cases"])
    ):
        raise SystemExit("Calibration-only source/model/contract must match the valid frozen baseline")
    return report


def _phase(output: Path, parent: dict[str, Any]) -> dict[str, Any]:
    path = output / "calibration-only-c21.json"
    if path.exists():
        phase = json.loads(path.read_text(encoding="utf-8"))
        if (
            phase["parent_run_id"] != parent["metadata"]["run_id"]
            or phase["source_sha256"] != parent["metadata"]["source_sha256"]
        ):
            raise SystemExit("Calibration-only state belongs to a different frozen run")
        return phase
    return {
        "phase": "calibration_only",
        "parent_run_id": parent["metadata"]["run_id"],
        "source_sha256": parent["metadata"]["source_sha256"],
        "contract_version": VERSION,
        "status": "incomplete",
        "excluded_from_baseline_score": True,
        "scenario_id": "D02",
        "sampling": "same_scenario_independent_new_answer",
        "cases": [],
        "evidence_full": [],
    }


def _finish(phase: dict[str, Any], judge: Any, parent: dict[str, Any], budget: MemberBudget, output: Path) -> int:
    for row in judge.records:
        row["calibration_only"] = True
    phase["evidence_full"] = judge.records
    phase["membership"] = budget.snapshot()
    phase["new_real_calls"] = phase["membership"]["run_calls_total"] - phase["calls_before"]
    if phase["status"] == "complete":
        judge.records = list(parent.get("evidence_full", [])) + judge.records
        phase["calibration"] = export_candidates(
            judge, output.parent / "calibration/candidates-c2.1.md", valid_run=True
        )
    write_json(output / "calibration-only-c21.json", phase)
    return 0 if phase["status"] == "complete" else 3 if phase.get("resume_at") else 2


def run_calibration(output: Path, ledger: Path | None, freeze: Path | None) -> int:
    from tools.eval.runner_v2 import _prepare

    parent = _parent(output, freeze)
    phase = _phase(output, parent)
    if phase["status"] == "complete":
        return 0
    if ledger is None:
        raise SystemExit("Calibration-only calls require the same shared membership ledger")
    if ledger_identity(ledger) != parent["metadata"].get("member_ledger_identity"):
        raise SystemExit("Calibration-only calls must use the baseline's original shared membership ledger")
    budget = MemberBudget(ledger, parent["metadata"]["run_id"])
    if budget.snapshot()["run_calls_total"] < parent["metadata"].get("membership", {}).get("run_calls_total", 0):
        raise SystemExit("Calibration membership ledger lost the baseline's actual-call history")
    judge, target = _prepare("live", budget=budget, freeze=freeze)
    judge.run_id = phase["parent_run_id"] + ":calibration"
    judge.records = list(phase["evidence_full"])
    phase.setdefault("calls_before", budget.snapshot()["run_calls_total"])
    try:
        if budget.snapshot().get("reason") == "quota_5h":
            budget.resume_once()
        budget.before_batch(["D02"])
        scenario = migrate(next(case for case in load_scenarios() if case.id == "D02"))[0]
        result = evaluate_scenario(scenario, target, target_name="v3", judge=judge)
        phase["cases"].append(result)
        if result.get("stop_reason"):
            raise ProviderStopped(
                result["stop_reason"], result.get("stop_role", "target"), resume_at=budget.snapshot().get("resume_at")
            )
        if is_infrastructure_failure(result):
            phase["status"] = "incomplete"
        else:
            budget.finish_batch()
            phase.update(status="complete", stop_reason=None, resume_at=None)
    except ProviderStopped as exc:
        phase.update(status="incomplete", stop_reason=exc.reason, resume_at=exc.resume_at)
        if exc.reason == "quota_weekly":
            phase["warning"] = "线上可能受影响"
    except BaseException as exc:
        phase.update(status="incomplete", execution_error_code=type(exc).__name__)
        raise
    finally:
        try:
            target.close()
        finally:
            phase["evidence_full"] = judge.records
            phase["membership"] = budget.snapshot()
            phase["new_real_calls"] = phase["membership"]["run_calls_total"] - phase["calls_before"]
            write_json(output / "calibration-only-c21.json", phase)
    return _finish(phase, judge, parent, budget, output)

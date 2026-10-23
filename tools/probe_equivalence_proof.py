"""A Core approval consumes verified local PG checks, never an external boolean."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from mingjing_core.models.quota_delegated import _SEAL, DelegatedApproval, token_parts
from mingjing_core.models.quota_types import GuardRejected
from tools.probe_equivalence_cases import CASES, MAX_ATTEMPTS
from tools.probe_equivalence_control import ProbeControl, ProbeControlError, digest

MODELS = ("k3", "k3-256k")
EXPECTED = frozenset(
    (model, case.ident, step) for case in CASES for model in MODELS for step in range(1, 3 if case.roundtrip else 2)
)
RESULT_FIELDS = frozenset(
    {
        "model",
        "scenario",
        "step",
        "passed",
        "response_model",
        "text_chars",
        "tool_count",
        "reasoning_present",
        "usage",
        "usage_known",
        "elapsed_ms",
        "effort",
    }
)


def contract_digest() -> str:
    return digest(
        {
            "models": MODELS,
            "max_attempts": MAX_ATTEMPTS,
            "cases": [
                {
                    "id": case.ident,
                    "prompt": case.prompt,
                    "roundtrip": case.roundtrip,
                    "tools": [{"name": tool.name, "schema": tool.parameters} for tool in case.tools],
                }
                for case in CASES
            ],
        }
    )


def _check_rows(session: dict, checks: list[dict], physical: list[dict]) -> bool:
    usage = {row["attempt_id"]: row for row in physical}
    keys = set()
    for check in checks:
        result = check["result"]
        row = usage.get(check["attempt_id"])
        key = (check["model"], check["scenario"], check["step"])
        expected_run = f"{session['evaluation_session_id']}:{key[0]}:{key[1]}:{key[2]}"
        if (
            key not in EXPECTED
            or key in keys
            or not isinstance(result, dict)
            or set(result) != RESULT_FIELDS
            or type(result.get("passed")) is not bool
            or (result["model"], result["scenario"], result["step"]) != key
            or row is None
            or row["provider"] != "kimi_code"
            or row["lane"] != "probe"
            or row["status"] != "ok"
            or row["finished_at"] is None
            or row["role"] != "evaluation"
            or row["run_id"] != expected_run
            or row["model"] != key[0]
            or row["scenario_id"] != key[1]
            or digest(row) != check["usage_sha256"]
            or token_parts(row["authorization_id"]) != (session["candidate_commit"], "eq")
        ):
            raise ProbeControlError("证明检查与真实调用不一致")
        keys.add(key)
    return (
        keys == EXPECTED
        and len(physical) == MAX_ATTEMPTS
        and {check["attempt_id"] for check in checks} == set(usage)
        and not session["prior_attempt_ids"]
    )


def proof_report(control: ProbeControl, guard: Any, session_id: str) -> dict[str, Any]:
    session = control.session(guard, session_id)
    if session["contract_sha256"] != contract_digest():
        raise ProbeControlError("固定探针契约改变")
    checks, physical = control.checks(session_id), control.physical(guard)
    complete = _check_rows(session, checks, physical)
    equivalent = all(row["result"]["passed"] for row in checks) if complete else None
    result = {
        "schema": "k3-equivalence-proof-v1",
        "evaluation_session_id": session_id,
        "candidate_commit": session["candidate_commit"],
        "source_sha256": session["source_sha256"],
        "contract_sha256": session["contract_sha256"],
        "account_id": session["account_id"],
        "ledger_identity": session["ledger_identity"],
        "location_id": session["location_id"],
        "control_schema": control.schema,
        "control_location_id": session["control_location_id"],
        "mode": session["mode"],
        "at": session["at"].isoformat(),
        "complete": complete,
        "equivalent": equivalent,
        "selected_model": None if not complete else "k3-256k" if equivalent else "k3",
        "model_calls": len(physical),
        "physical_attempt_limit": MAX_ATTEMPTS,
        "budget_remaining": max(0, MAX_ATTEMPTS - len(physical)),
        "required_steps_remaining": MAX_ATTEMPTS - len(checks),
        "budget_sufficient": not session["prior_attempt_ids"] and len(physical) <= len(checks),
        "prior_attempt_ids": session["prior_attempt_ids"],
        "attempt_ids": [row["attempt_id"] for row in physical],
        "stop_kind": session["stop_kind"],
        "resume_at": session["resume_at"].isoformat() if session["resume_at"] else None,
        "records": [row["result"] for row in checks],
        "automatic_next_batch": True,
    }
    result["proof_sha256"] = digest(result)
    return result


def approval_from_equivalence(
    guard: Any,
    scripted: DelegatedApproval,
    proof: Any,
    *,
    control: ProbeControl,
    source_sha256: str,
) -> DelegatedApproval:
    scripted.check(guard.clock.now())
    if (
        scripted.equivalent is not None
        or not isinstance(proof, dict)
        or proof.get("schema") != "k3-equivalence-proof-v1"
    ):
        raise GuardRejected("manual_start_required")
    with control.exclusive(guard):
        actual = proof_report(control, guard, proof.get("evaluation_session_id", ""))
        if (
            actual != proof
            or actual["candidate_commit"] != scripted.candidate
            or actual["source_sha256"] != source_sha256
            or actual["mode"] != "live"
            or not actual["complete"]
            or type(actual["equivalent"]) is not bool
        ):
            raise GuardRejected("manual_start_required")
        state = guard.status()
        if state["stop_kind"]:
            raise GuardRejected(state["stop_kind"], state["resume_at"])
        equivalent = actual["equivalent"]
        return replace(
            scripted, equivalent=equivalent, _seal=(_SEAL, scripted.candidate, scripted.expires_at, equivalent)
        )


def load_core_approval(
    guard: Any,
    scripted: DelegatedApproval,
    proof_path: Path,
    *,
    control: ProbeControl,
    source_sha256: str,
) -> DelegatedApproval:
    if proof_path.stat().st_size > 65536:
        raise GuardRejected("manual_start_required")
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        raise GuardRejected("manual_start_required") from None
    return approval_from_equivalence(guard, scripted, proof, control=control, source_sha256=source_sha256)

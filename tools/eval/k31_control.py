"""R16 proof rechecks actual local PG observations; JSON alone never opens core."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.models.quota_delegated import token_parts
from mingjing_core.models.quota_r16 import K31ConnectionApproval, _core_approval
from mingjing_core.models.quota_types import GuardRejected
from tools.eval.k31_contract import EXPECTED, FIELDS, MODEL, contract_digest
from tools.probe_equivalence_control import ProbeControl, ProbeControlError, digest


def validate_check(session: dict, result: dict, physical: dict | None) -> None:
    if (
        not isinstance(result, dict)
        or set(result) != FIELDS
        or (result["scenario"], result["step"]) not in EXPECTED
        or type(result["passed"]) is not bool
        or result["model"] != MODEL
        or result["response_model"] != MODEL
        or result["effort"] != "high"
        or physical is None
        or physical["provider"] != "kimi_code"
        or physical["model"] != MODEL
        or physical["lane"] != "probe"
        or physical["role"] != "evaluation"
        or physical["status"] != "ok"
        or physical["finished_at"] is None
        or physical["scenario_id"] != result["scenario"]
        or physical["run_id"] != f"{session['evaluation_session_id']}:{MODEL}:{result['scenario']}:{result['step']}"
        or token_parts(physical["authorization_id"]) != (session["candidate_commit"], "k31-connect")
        or type(result["input_actual"]) is not int
        or result["input_actual"] <= 0
        or result["input_actual"] != physical["input_tokens"]
        or type(result["input_estimated"]) is not int
        or result["input_estimated"] <= 0
    ):
        raise ProbeControlError("K31检查与固定合同或物理账本不符")
    ratio, factor = Decimal(result["input_ratio"]), Decimal(result["factor"])
    if not ratio.is_finite() or not factor.is_finite() or factor < Decimal("1.15"):
        raise ProbeControlError("K31输入计量系数无效")
    if ratio != Decimal(result["input_actual"]) / Decimal(result["input_estimated"]):
        raise ProbeControlError("K31输入计量比例与物理账本不符")


class K31Control(ProbeControl):
    def record(self, guard: Any, session_id: str, attempt_id: str, result: dict) -> None:
        session = self.session(guard, session_id)
        physical = next((row for row in self.physical(guard) if row["attempt_id"] == attempt_id), None)
        validate_check(session, result, physical)
        with self.connect() as connection:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}(evaluation_session_id,attempt_id,model,scenario,step,usage_sha256,result) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s)"
                ).format(self.table("probe_checks")),
                (session_id, attempt_id, MODEL, result["scenario"], result["step"], digest(physical), Jsonb(result)),
            )

    def report(self, guard: Any, session_id: str) -> dict:
        session = self.session(guard, session_id)
        if session["contract_sha256"] != contract_digest():
            raise ProbeControlError("K31接入合同改变")
        checks = self.checks(session_id)
        physical = [
            row
            for row in self.physical(guard)
            if token_parts(row["authorization_id"]) == (session["candidate_commit"], "k31-connect")
        ]
        usage = {row["attempt_id"]: row for row in physical}
        observed = set()
        for check in checks:
            row = usage.get(check["attempt_id"])
            validate_check(session, check["result"], row)
            key = check["scenario"], check["step"]
            if key in observed or digest(row) != check["usage_sha256"]:
                raise ProbeControlError("K31检查重复或物理账本已改变")
            observed.add(key)
        complete = observed == EXPECTED and all(check["result"]["passed"] for check in checks)
        state = guard.status()
        result = {
            "schema": "k31-connection-proof-r16",
            "evaluation_session_id": session_id,
            "candidate_commit": session["candidate_commit"],
            "source_sha256": session["source_sha256"],
            "contract_sha256": session["contract_sha256"],
            "account_id": session["account_id"],
            "ledger_identity": session["ledger_identity"],
            "location_id": session["location_id"],
            "control_location_id": session["control_location_id"],
            "control_schema": self.schema,
            "mode": session["mode"],
            "complete": complete and session["status"] == "complete",
            "model": MODEL,
            "effort": "high",
            "records": [check["result"] for check in checks],
            "model_calls": len(physical),
            "attempt_ids": [row["attempt_id"] for row in physical],
            "wasted_attempt_ids": [
                row["attempt_id"]
                for row in physical
                if row["attempt_id"] not in {check["attempt_id"] for check in checks}
            ],
            "stop_kind": state["stop_kind"],
            "resume_at": state["resume_at"].isoformat() if state["resume_at"] else None,
            "factor": str(max([Decimal("1.15"), *[Decimal(check["result"]["factor"]) for check in checks]])),
        }
        result["proof_sha256"] = digest(result)
        return result


def core_approval(guard: Any, scripted: K31ConnectionApproval, proof: dict, control: K31Control):
    if not isinstance(scripted, K31ConnectionApproval) or not isinstance(proof, dict):
        raise GuardRejected("manual_start_required")
    scripted.check(guard.clock.now())
    with control.exclusive(guard):
        actual = control.report(guard, proof.get("evaluation_session_id", ""))
        if (
            actual != proof
            or actual["mode"] != "live"
            or not actual["complete"]
            or actual["candidate_commit"] != scripted.candidate
            or actual["source_sha256"] != scripted.source_sha256
            or actual["stop_kind"]
            or actual["model_calls"] > 20
        ):
            raise GuardRejected("manual_start_required")
        return _core_approval(scripted, actual["proof_sha256"], actual["factor"])

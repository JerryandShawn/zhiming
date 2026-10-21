"""Normalize trusted completed CaseUpdate intent without treating history as current state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from psycopg import sql
from pydantic import ValidationError

from mingjing_core.agent.context_types import ContextBuild
from mingjing_core.agent.journal import Journal
from mingjing_core.application.agent_pending_effects import _attest, _initial, _original_call, _source
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


@dataclass(frozen=True)
class CaseEffectIntent:
    run: dict[str, Any] = field(repr=False)
    base: ContextBuild = field(repr=False)
    args: dict[str, Any] = field(repr=False)
    versions: dict[str, int] = field(repr=False)
    rows: list[dict[str, Any]] = field(repr=False)
    mutation: dict[str, Any] = field(repr=False)
    operation: str = field(repr=False)
    source: dict[str, Any] = field(repr=False)
    start: int
    end: int


def load_completed_intent(repo: PostgresRepository, run: Mapping[str, Any], sequence: int) -> CaseEffectIntent:
    return _load_intent(repo, run, sequence, pending=False)


def load_pending_intent(repo: PostgresRepository, run: Mapping[str, Any], sequence: int) -> CaseEffectIntent:
    return _load_intent(repo, run, sequence, pending=True)


def _step_state(step: dict, sequence: int, pending: bool) -> None:
    expected = "started" if pending else "completed"
    if (
        step["seq"] != sequence
        or (step["kind"], step["name"], step["status"]) != ("tool", "case_update", expected)
        or step["error_code"] is not None
        or (pending and (step["output"] is not None or step["finished_at"] is not None or step["usage"] != {}))
        or (not pending and step["finished_at"] is None)
    ):
        raise EvidenceError("事项版本证据不能改变实际步骤确认状态")


def _load_intent(repo: PostgresRepository, run: Mapping[str, Any], sequence: int, *, pending: bool) -> CaseEffectIntent:
    if type(sequence) is not int or sequence < 1:
        raise EvidenceError("已完成事项步骤序号无效")
    with repo.transaction(run["owner"]) as connection:
        current = repo._run(Journal(repo, run["owner"])._leased(connection, run))
        rows = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq<=%s ORDER BY seq FOR UPDATE"
            ).format(repo.table("core_run_steps")),
            (current["owner"], current["id"], current["retry_epoch"], sequence),
        ).fetchall()
        if not rows or rows[-1]["seq"] != sequence:
            raise EvidenceError("已完成事项步骤缺失")
        step = rows[-1]
        _step_state(step, sequence, pending)
        operation = f"run:{current['id']}:e{current['retry_epoch']}:s{sequence}"
        mutation = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation='agent_case_update' AND request_key=%s").format(
                repo.table("core_mutation_requests")
            ),
            (current["owner"], operation),
        ).fetchone()
        if mutation is None:
            raise EvidenceError("事项写入缺少实际mutation证明")
        try:
            base = _initial(repo, current)
            args, versions = _original_call(repo, current, rows, base)
            receipt = mutation["receipt"]
            if not pending:
                result = ToolResult.model_validate(step["output"])
                if not result.ok or result.ends_turn:
                    raise EvidenceError("事项引用没有真实成功的完成输出")
                receipt = result.receipt
            _check_intent(current, base, args, versions, receipt, mutation)
            source, start, end = _source(repo, current, args, versions)
        except (KeyError, TypeError, ValueError, ValidationError):
            raise EvidenceError("已完成事项写入的持久证明结构无效") from None
        return CaseEffectIntent(current, base, args, versions, rows, mutation, operation, source, start, end)


def _check_intent(run: dict, base: ContextBuild, args: dict, versions: dict, receipt: dict, mutation: dict) -> None:
    key = entity_dependency("case", args["id"])
    expected = {"write_status": "saved", "kind": "case", "id": args["id"], "revision": args["expected_revision"] + 1}
    if (
        (run["thread_id"] or "life:" + run["subject"]) != "life:" + run["subject"]
        or args["id"] not in run["request"].get("case_ids", [])
        or key not in base.injected_versions
        or type(versions.get(key)) is not int
        or versions[key] > args["expected_revision"]
        or mutation["fingerprint"] != fingerprint(args)
        or fingerprint(receipt) != fingerprint(expected)
        or fingerprint(mutation["receipt"]) != fingerprint(expected)
    ):
        raise EvidenceError("事项写入与正规调用、实际范围或精确回执不符")


def attest_completed_case_effect(
    repo: PostgresRepository, run: Mapping[str, Any], sequence: int
) -> tuple[ContextBuild, dict[str, Any], dict[str, Any]]:
    with repo.transaction(run["owner"]) as connection:
        proof = load_completed_intent(repo, run, sequence)
        receipt = _attest(repo, connection, proof.run, proof.rows, proof.mutation, proof.operation)
        return proof.base, proof.args, receipt

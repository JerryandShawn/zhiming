"""Attest all current-epoch revisions, never infer a missing intermediate effect."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.application.agent_case_completed import CaseEffectIntent, load_completed_intent, load_pending_intent
from mingjing_core.application.agent_case_effect_attestation import verify_effect
from mingjing_core.application.agent_case_effect_marker import marker_cases
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import fingerprint


def assert_case_effect_chain(repo: Any, run: dict, alias: dict, current: dict) -> None:
    _assert_chain(repo, run, alias, current)


def pending_chain_receipt(repo: Any, run: dict, sequence: int) -> dict[str, Any]:
    proof = load_pending_intent(repo, run, sequence)
    current = repo.get(run["owner"], "case", proof.args["id"])
    alias = next(
        (value for value in proof.base.alias_map.values() if value["kind"] == "case" and value["id"] == current["id"]),
        None,
    )
    if alias is None:
        raise EvidenceError("未确认事项版本链没有受信初始引用身份")
    _assert_chain(repo, run, alias, current, pending=proof)
    return dict(proof.mutation["receipt"], _operation=proof.operation)


def _assert_chain(repo: Any, run: dict, alias: dict, current: dict, *, pending: CaseEffectIntent | None = None) -> None:
    cases = marker_cases(run)
    sequences = cases.get(current["id"]) if cases is not None else None
    if not sequences or len(sequences) != current["revision"] - alias["revision"]:
        raise EvidenceError("事项版本链缺少连续的实际更新证据")
    initial = (
        pending
        if pending and sequences[0] == pending.rows[-1]["seq"]
        else load_completed_intent(repo, run, sequences[0])
    ).base
    if not any(fingerprint(value) == fingerprint(alias) for value in initial.alias_map.values()):
        raise EvidenceError("事项版本链没有受信初始引用身份")
    for ident, selected_sequences in cases.items():
        selected = repo.get(run["owner"], "case", ident)
        if selected["subject_id"] != run["subject"] or repo.is_revoked(run["owner"], "case", ident):
            raise EvidenceError("事项版本链当前人物或授权已失效")
        original = next(
            (value for value in initial.alias_map.values() if value["kind"] == "case" and value["id"] == ident), None
        )
        if original is None:
            raise EvidenceError("事项版本链扩大了受信初始事项身份")
        _selected_chain(repo, run, original, selected, selected_sequences, pending=pending)


def _selected_chain(
    repo: Any, run: dict, alias: dict, current: dict, sequences: list[int], *, pending: CaseEffectIntent | None = None
) -> None:
    if len(sequences) != current["revision"] - alias["revision"]:
        raise EvidenceError("事项版本链没有覆盖完整修订区间")
    previous = None
    for offset, sequence in enumerate(sequences):
        proof = (
            pending if pending and sequence == pending.rows[-1]["seq"] else load_completed_intent(repo, run, sequence)
        )
        if not any(fingerprint(value) == fingerprint(alias) for value in proof.base.alias_map.values()):
            raise EvidenceError("事项版本链没有受信初始引用身份")
        before, after = verify_effect(repo, proof, sequence)
        if (
            proof.args["id"] != current["id"]
            or before["revision"] != alias["revision"] + offset
            or previous is not None
            and fingerprint(previous) != fingerprint(before)
        ):
            raise EvidenceError("事项版本链存在缺环、外部插写或错误顺序")
        previous = after
    key = entity_dependency("case", current["id"])
    pending_seq = pending.rows[-1]["seq"] if pending and pending.args["id"] == current["id"] else None
    allowed = {current["revision"] - 1, current["revision"]} if pending_seq else {current["revision"]}
    if run["state_version"].get(key) not in allowed or fingerprint(previous) != fingerprint(current):
        raise EvidenceError("事项版本链终点与当前真实资料不符")
    _complete_steps(repo, run, current, sequences, pending_seq=pending_seq)


def _complete_steps(
    repo: Any, run: dict, current: dict, sequences: list[int], *, pending_seq: int | None = None
) -> None:
    with repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT seq,output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='tool' "
                "AND name='case_update' AND status='completed' AND error_code IS NULL ORDER BY seq"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"]),
        ).fetchall()
    actual = []
    for step in rows:
        output = step["output"] or {}
        receipt = output.get("receipt") or {}
        if (
            receipt.get("write_status") == "saved"
            and receipt.get("kind") == "case"
            and receipt.get("id") == current["id"]
        ):
            actual.append(step["seq"])
    if pending_seq:
        actual.append(pending_seq)
    if actual != sequences:
        raise EvidenceError("事项版本标记不能遗漏或新增完成步骤")

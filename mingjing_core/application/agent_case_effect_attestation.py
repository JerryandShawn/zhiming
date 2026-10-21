"""Recompute each private Case effect from a genuine completed model/tool intent."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.application.agent_case_changes import case_update_payload
from mingjing_core.application.agent_case_completed import CaseEffectIntent
from mingjing_core.application.agent_case_effect_marker import SCHEMA, STAGE, marker_cases
from mingjing_core.application.agent_case_effect_records import check_size, effect_id, linked_metadata
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.memory.tokenize import searchable_data
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import fingerprint

OUTPUT_FIELDS = {
    "arguments",
    "before",
    "update_input",
    "versions",
    "context_source_ids",
    "after",
    "receipt",
    "operation_fingerprint",
    "effect_created_at",
}
RESERVED = {"id", "owner", "owner_user_id", "subject", "subject_id", "case_id", "revision", "created_at", "updated_at"}


def verify_effect(repo: Any, proof: CaseEffectIntent, sequence: int) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return _verify_effect(repo, proof, sequence)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise EvidenceError("事项版本证据的持久结构无效") from None


def _verify_effect(repo: Any, proof: CaseEffectIntent, sequence: int) -> tuple[dict[str, Any], dict[str, Any]]:
    run = proof.run
    ident = effect_id(run["id"], run["retry_epoch"], sequence)
    saved = repo.get(run["owner"], "runtime_step", ident, include_deleted=True)
    output = saved.get("output")
    if (
        saved["status"] != "active"
        or saved["subject_id"] != run["subject"]
        or saved.get("schema") != SCHEMA
        or saved.get("stage") != STAGE
        or (saved.get("run_id"), saved.get("epoch"), saved.get("seq")) != (run["id"], run["retry_epoch"], sequence)
        or saved.get("request_sha256") != fingerprint(run["request"])
        or saved.get("target_case_id") != proof.args["id"]
        or saved.get("case_ids") != run["request"].get("case_ids", [])
        or not isinstance(output, dict)
        or set(output) != OUTPUT_FIELDS
        or saved.get("output_sha256") != fingerprint(output)
        or repo.is_revoked(run["owner"], "runtime_step", ident)
    ):
        raise EvidenceError("事项版本证据损坏、失效或范围不符")
    check_size(output)
    _versions(proof, output)
    sources, facts = linked_metadata(output)
    if saved.get("source_ids") != sources or saved.get("fact_ids") != facts:
        raise EvidenceError("事项版本证据的隐私闭包不符")
    before, after = output["before"], output["after"]
    expected = dict(before, **case_update_payload(before, proof.args, proof.source, proof.start, proof.end))
    if fingerprint(output["arguments"]) != fingerprint(proof.args) or fingerprint(
        output["update_input"]
    ) != fingerprint(expected):
        raise EvidenceError("事项版本证据与正规修改意图不符")
    _operation(repo, proof, saved, output)
    if fingerprint(after) != fingerprint(_after(before, expected, run, output["effect_created_at"])):
        raise EvidenceError("事项实际更新后投影与精确输入不符")
    return before, after


def _versions(proof: CaseEffectIntent, output: dict) -> None:
    versions = output["versions"]
    key = entity_dependency("case", proof.args["id"])
    if not isinstance(versions, dict) or versions.get(key) != proof.args["expected_revision"]:
        raise EvidenceError("事项版本证据的更新前版本不符")
    cases = marker_cases(proof.run) or {}
    sequence = proof.rows[-1]["seq"]
    for name, value in versions.items():
        case_id = name.removeprefix("entity:case:") if name.startswith("entity:case:") else None
        if case_id in cases:
            initial = proof.base.injected_versions.get(name)
            expected = initial + sum(seq < sequence for seq in cases[case_id]) if type(initial) is int else None
            if type(value) is not int or value != expected or proof.versions.get(name, value) > value:
                raise EvidenceError("事项版本证据改变了正规事项修订顺序")
        elif value != proof.run["state_version"].get(name) or proof.versions.get(name, value) != value:
            raise EvidenceError("事项版本证据改变了正规模型依赖")
    if set(proof.versions) - set(versions):
        raise EvidenceError("事项版本证据遗漏了正规模型依赖")
    context = output["context_source_ids"]
    if not isinstance(context, list) or any(
        not isinstance(value, str) or "message:" + value not in versions for value in context
    ):
        raise EvidenceError("事项版本证据的原话范围无效")
    before = output["before"]
    if (
        before.get("owner") != proof.run["owner"]
        or before.get("subject_id") != proof.run["subject"]
        or before.get("id") != proof.args["id"]
        or type(before.get("revision")) is not int
        or before["revision"] != proof.args["expected_revision"]
    ):
        raise EvidenceError("事项版本证据的更新前身份不符")


def _operation(repo: Any, proof: CaseEffectIntent, saved: dict, output: dict) -> None:
    before, after, run = output["before"], output["after"], proof.run
    value = ["case", before["id"], run["subject"], before["case_id"], output["update_input"]]
    digest = fingerprint(value)
    with repo.transaction(run["owner"]) as connection:
        operation = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation_id=%s AND kind='case' AND result_id=%s").format(
                repo.table("core_operations")
            ),
            (run["owner"], proof.operation + ":case", before["id"]),
        ).fetchone()
    receipt = {"write_status": "saved", "kind": "case", "id": before["id"], "revision": before["revision"] + 1}
    if (
        operation is None
        or operation["fingerprint"] != digest
        or output["operation_fingerprint"] != digest
        or operation["created_at"] != proof.mutation["created_at"]
        or operation["created_at"].isoformat() != output["effect_created_at"]
        or saved["created_at"] != output["effect_created_at"]
        or after.get("revision") != before["revision"] + 1
        or fingerprint(output["receipt"]) != fingerprint(receipt)
        or fingerprint(proof.mutation["receipt"]) != fingerprint(receipt)
    ):
        raise EvidenceError("事项版本证据与真实效果、回执或原事务时间不符")


def _after(before: dict, update: dict, run: dict, stamp: str) -> dict[str, Any]:
    payload = searchable_data(
        "case", {key: value for key, value in update.items() if key not in RESERVED and key != "status"}
    )
    return dict(
        payload,
        id=before["id"],
        owner=run["owner"],
        owner_user_id=run["owner"],
        subject=run["subject"],
        subject_id=run["subject"],
        case_id=before["case_id"],
        status=update["status"],
        revision=before["revision"] + 1,
        created_at=before["created_at"],
        updated_at=stamp,
    )

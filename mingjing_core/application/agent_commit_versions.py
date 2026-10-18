"""Own writes need an exact persisted receipt, never just an old operation prefix."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg import sql

from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.dependencies import entity_dependency, lineage_key
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


class RegenerationRequired(RevisionConflict):
    code = "V4_REGENERATION_REQUIRED"


def persisted_receipts(repo: PostgresRepository, run: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    owner, ident, epoch = run["owner"], run["id"], run["retry_epoch"]
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT seq,name,output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                "AND kind='tool' AND status='completed' AND error_code IS NULL ORDER BY seq"
            ).format(repo.table("core_run_steps")),
            (owner, ident, epoch),
        ).fetchall()
        receipts = []
        for row in rows:
            receipt = (row["output"] or {}).get("receipt")
            if receipt is None:
                continue
            if not isinstance(receipt, dict):
                raise EvidenceError("工具回执结构无效")
            operation = f"run:{ident}:e{epoch}:s{row['seq']}"
            stored = connection.execute(
                sql.SQL("SELECT receipt FROM {} WHERE owner=%s AND operation=%s AND request_key=%s").format(
                    repo.table("core_mutation_requests")
                ),
                (owner, "agent_" + row["name"], operation),
            ).fetchone()
            if stored is None or fingerprint(stored["receipt"]) != fingerprint(receipt):
                raise EvidenceError("步骤回执缺少实际写入证明")
            receipts.append(dict(receipt, _operation=operation))
    return tuple(receipts)


def reconcile_versions(repo: PostgresRepository, run: Mapping[str, Any], versions: Mapping[str, int]) -> dict[str, int]:
    """Return current exact versions only for effects proven by this epoch's journal."""
    owner = run["owner"]
    receipts = persisted_receipts(repo, run)
    result = dict(versions)
    with repo.transaction(owner) as connection:
        for key, expected in versions.items():
            actual = repo._version(connection, owner, key)
            if actual == expected:
                continue
            kind, _, ident = lineage_key(key).partition(":")
            row = repo.get(owner, kind, ident, include_deleted=True)
            if row["subject_id"] != run["subject"] or row["status"] in {"deleted", "stopped"}:
                raise RevisionConflict("本轮依赖已失效")
            if key != entity_dependency(kind, ident) or not _own_revision(connection, repo, run, row, kind, receipts):
                raise RevisionConflict("依赖变化不是本轮已证实的写入")
            result[key] = actual
    return result


def _own_revision(
    connection: Any,
    repo: PostgresRepository,
    run: Mapping[str, Any],
    row: Mapping[str, Any],
    kind: str,
    receipts: tuple[dict[str, Any], ...],
) -> bool:
    for receipt in receipts:
        if (
            receipt.get("write_status") != "saved"
            or receipt.get("kind") != kind
            or receipt.get("id", receipt.get("fact_id")) != row["id"]
            or type(receipt.get("revision")) is not int
            or receipt["revision"] != row["revision"]
        ):
            continue
        prefix = receipt["_operation"] + ":"
        operation = connection.execute(
            sql.SQL(
                "SELECT 1 FROM {} WHERE owner=%s AND kind=%s AND result_id=%s AND left(operation_id,%s)=%s LIMIT 1"
            ).format(repo.table("core_operations")),
            (run["owner"], kind, row["id"], len(prefix), prefix),
        ).fetchone()
        if operation is not None:
            return True
    return False


def assert_no_withdrawal(
    repo: PostgresRepository,
    run: Mapping[str, Any],
    versions: Mapping[str, int],
    snapshot_revision: int,
) -> None:
    keys = {lineage_key(key) for key in versions}
    for revoked in repo.revocations(run["owner"]):
        if revoked["revision"] <= snapshot_revision:
            continue
        key = revoked["kind"] + ":" + revoked["entity_id"]
        source = "message:" + str(revoked["metadata"].get("message_id", ""))
        if key in keys or revoked["kind"] == "source_span" and source in keys:
            if run["retry_epoch"] >= 1:
                raise EvidenceError("本轮重新生成后来源再次撤销，不能继续发布")
            raise RegenerationRequired("本轮采用的来源已撤销，需要一次清洁上下文重新生成")
    if "message:" + str(run["request"].get("source_message_id")) not in keys:
        raise ScopeError("提交缺少当前用户原话依赖")

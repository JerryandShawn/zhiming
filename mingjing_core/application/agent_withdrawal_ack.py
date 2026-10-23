"""A deleted fact can be acknowledged after regeneration without restoring old outputs.

These receipts only enter the final public envelope. They never authorize own
writes, dependency reconciliation or an alias from the withdrawn epoch.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg import sql

from mingjing_core.agent.tools.parameters import MemoryForget
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import fingerprint


def current_source(repo: Any, run: Mapping[str, Any], versions: Mapping[str, int]) -> str:
    source_id = run["request"].get("source_message_id")
    source = repo.get(run["owner"], "message", source_id, include_deleted=True)
    if (
        source["status"] != "active"
        or source.get("role") != "user"
        or source["subject_id"] != run["subject"]
        or source.get("thread_id") != run["thread_id"]
        or source.get("policy", {}).get("origin") != "current_user"
        or source.get("policy", {}).get("run_context") is not True
        or versions.get("message:" + source_id) != source["revision"]
        or run["state_version"].get("message:" + source_id) != source["revision"]
        or repo.is_revoked(run["owner"], "message", source_id)
        or any(
            row["kind"] == "source_span" and row["metadata"].get("message_id") == source_id
            for row in repo.revocations(run["owner"])
        )
    ):
        raise EvidenceError("撤销确认的当前原话已改变或不可用")
    return source_id


def verified_receipt(
    repo: Any, connection: Any, run: Mapping[str, Any], source_id: str, stored: Mapping[str, Any]
) -> dict[str, Any]:
    receipt = stored["receipt"]
    fields = {"write_status", "fact_id", "kind", "affected_ids"}
    if (
        not isinstance(receipt, dict)
        or set(receipt) - fields
        or receipt.get("write_status") != "deleted"
        or receipt.get("kind") != "fact"
        or not isinstance(receipt.get("fact_id"), str)
        or not 1 <= len(receipt["fact_id"]) <= 200
    ):
        raise EvidenceError("撤销确认不是无正文删除回执")
    arguments = MemoryForget(fact_id=receipt["fact_id"], message_id=source_id).model_dump()
    if fingerprint(arguments) != stored["fingerprint"]:
        raise EvidenceError("撤销确认参数指纹与当前原话不符")
    affected = receipt.get("affected_ids", [receipt["fact_id"]])
    if (
        not isinstance(affected, list)
        or not 1 <= len(affected) <= 1024
        or receipt["fact_id"] not in affected
        or any(not isinstance(ident, str) or not 1 <= len(ident) <= 200 for ident in affected)
    ):
        raise EvidenceError("撤销确认目标无效")
    for ident in affected:
        row = connection.execute(
            sql.SQL("SELECT subject,case_id,status,data FROM {} WHERE owner=%s AND kind='fact' AND id=%s").format(
                repo.table("core_entities")
            ),
            (run["owner"], ident),
        ).fetchone()
        if (
            not row
            or row["status"] != "deleted"
            or row["data"] != {}
            or row["subject"] != run["subject"]
            or row["case_id"]
            and row["case_id"] not in run["request"].get("case_ids", [])
            or not repo.is_revoked(run["owner"], "fact", ident)
        ):
            raise EvidenceError("撤销确认缺少同人物真实清空与撤销账本")
    return dict(receipt)


def withdrawal_acknowledgements(repo: Any, run: Mapping[str, Any], versions: Mapping[str, int]) -> tuple[dict, ...]:
    if getattr(repo._local, "connection", None) is None:
        raise EvidenceError("撤销确认只能在最终提交事务内组装")
    with repo.transaction(run["owner"]) as connection:
        actual = repo._leased(connection, run["owner"], run["id"], run["lease_token"])
        if (
            actual["runtime"] != "v4"
            or actual["retry_epoch"] != run["retry_epoch"]
            or actual["subject"] != run["subject"]
        ):
            raise EvidenceError("撤销确认不属于当前执行身份")
        regenerations = actual["usage"].get("agent_runtime", {}).get("regenerations")
        if actual["retry_epoch"] != 1 or type(regenerations) is not int or regenerations != 1:
            return ()
        steps = connection.execute(
            sql.SQL(
                "SELECT seq FROM {} WHERE owner=%s AND run_id=%s AND epoch=0 "
                "AND kind='tool' AND name='memory_forget' AND output IS NULL "
                "AND error_code='SOURCE_REVOKED' AND status IN ('started','completed') ORDER BY seq"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"]),
        ).fetchall()
        if not steps:
            return ()
        source_id = current_source(repo, actual, versions)
        receipts = []
        for step in steps:
            key = f"run:{run['id']}:e0:s{step['seq']}"
            stored = connection.execute(
                sql.SQL(
                    "SELECT fingerprint,receipt FROM {} WHERE owner=%s "
                    "AND operation='agent_memory_forget' AND request_key=%s"
                ).format(repo.table("core_mutation_requests")),
                (run["owner"], key),
            ).fetchone()
            if stored is not None:
                receipt = verified_receipt(repo, connection, actual, source_id, stored)
                if receipt not in receipts:
                    receipts.append(receipt)
        return tuple(receipts)

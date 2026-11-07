"""Exact native slot-change proof for historical facts in an updated receipt."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg import sql

from mingjing_core.domain.contracts import ScopeError


def affected_revision(connection: Any, repo: Any, run: Mapping, row: Mapping, receipt: Mapping) -> bool:
    if receipt.get("write_status") != "updated" or receipt.get("kind") != "fact":
        return False
    affected = receipt.get("affected_ids", [])
    changes = receipt.get("ids", [])
    if not isinstance(affected, list) or row["id"] not in affected or not isinstance(changes, list):
        return False
    try:
        new = repo.get(run["owner"], "fact", receipt.get("id", receipt.get("fact_id")), include_deleted=True)
    except (ScopeError, ValueError, TypeError):
        return False
    if (
        row["subject_id"] != run["subject"]
        or row["status"] != "active"
        or new["subject_id"] != run["subject"]
        or new["status"] != "active"
        or type(receipt.get("revision")) is not int
        or new["revision"] != receipt["revision"]
        or row.get("superseded_by") != new["id"]
        or new.get("supersedes") != row["id"]
        or not row.get("valid_to")
        or row["valid_to"] != new.get("valid_from")
    ):
        return False
    prefix = receipt["_operation"] + ":"
    for ident in changes:
        if not isinstance(ident, str):
            return False
        try:
            change = repo.get(run["owner"], "proposal", ident, include_deleted=True)
        except ScopeError:
            continue
        if (
            change["subject_id"] != run["subject"]
            or change["status"] != "applied"
            or type(change["revision"]) is not int
            or change["revision"] != 1
            or change.get("kind") != "memory2_slot_undo"
            or change.get("fact_ids") != [row["id"], new["id"]]
            or type(change.get("old_revision")) is not int
            or change["old_revision"] != row["revision"]
            or type(change.get("new_revision")) is not int
            or change["new_revision"] != new["revision"]
        ):
            continue
        proven = connection.execute(
            sql.SQL(
                "SELECT kind,result_id FROM {} WHERE owner=%s AND left(operation_id,%s)=%s "
                "AND ((kind='fact' AND result_id IN (%s,%s)) OR (kind='proposal' AND result_id=%s))"
            ).format(repo.table("core_operations")),
            (run["owner"], len(prefix), prefix, row["id"], new["id"], ident),
        ).fetchall()
        if {(item["kind"], item["result_id"]) for item in proven} == {
            ("fact", row["id"]),
            ("fact", new["id"]),
            ("proposal", ident),
        }:
            return True
    return False


def public_updated_receipts(repo: Any, run: Mapping, receipts: tuple[dict, ...]) -> tuple[dict, ...]:
    """Build a user-facing label from native facts without changing raw receipts."""
    result = []
    with repo.transaction(run["owner"]) as connection:
        for receipt in receipts:
            public = {key: value for key, value in receipt.items() if key != "_operation"}
            if receipt.get("write_status") == "updated" and receipt.get("kind") == "fact":
                for ident in receipt.get("affected_ids", []):
                    old = repo.get(run["owner"], "fact", ident, include_deleted=True)
                    if not affected_revision(connection, repo, run, old, receipt):
                        continue
                    new = repo.get(run["owner"], "fact", receipt.get("id", receipt.get("fact_id")))
                    before = str(old.get("summary") or old.get("content") or "原记忆")[:60]
                    after = str(new.get("summary") or new.get("content") or "新记忆")[:60]
                    public["summary"] = f"已更新：{before} → {after}［撤销］"
                    break
            result.append(public)
    return tuple(result)

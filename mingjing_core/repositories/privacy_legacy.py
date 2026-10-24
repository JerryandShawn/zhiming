"""Resolve a legacy withdrawal through persisted owner-local migration identities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from psycopg import sql

from mingjing_core.domain.contracts import EvidenceError

if TYPE_CHECKING:
    from mingjing_core.repositories.postgres import PostgresRepository


def legacy_memory_target(
    repo: PostgresRepository, connection: Any, owner: str, legacy_id: str
) -> tuple[str, str] | None:
    """Read within apply_privacy's transaction; its existing paths perform every write."""
    mapping = connection.execute(
        sql.SQL(
            "SELECT result_id FROM {} WHERE owner=%s AND source='memories' AND legacy_id=%s AND kind='fact' FOR SHARE"
        ).format(repo.table("core_legacy_map")),
        (owner, legacy_id),
    ).fetchone()
    if mapping is None or mapping["result_id"] is None:
        return None
    targets = connection.execute(
        sql.SQL(
            "SELECT kind,id,status,data FROM {} WHERE owner=%s AND id=%s AND kind IN ('fact','legacy') FOR UPDATE"
        ).format(repo.table("core_entities")),
        (owner, mapping["result_id"]),
    ).fetchall()
    if len(targets) > 1:
        raise EvidenceError("Legacy withdrawal target identity is ambiguous")
    if not targets:
        return None
    target = targets[0]
    if target["kind"] == "legacy" and target["status"] != "deleted":
        data = target["data"]
        if data.get("source") != "memories" or data.get("legacy_id") != legacy_id:
            raise EvidenceError("Legacy withdrawal target identity differs from its migration mapping")
    return target["kind"], target["id"]

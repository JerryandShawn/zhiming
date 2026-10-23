"""Body-free draw deletion lineage for the final candidate's restore replay."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from psycopg import sql

from mingjing_core.repositories.postgres import fingerprint

OPERATION = "tarot-delete:restore-v1"


def marker_identity(owner: str, draw_id: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    payload = {"owner": owner, "draw_id": draw_id, "version": 1}
    key = "withdrawal-draw-v1:" + fingerprint(payload)
    return key, payload, {"deleted": True, "deleted_ids": [draw_id], "kind": "draw"}


def exported_deleted_draws(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    pairs = {(row["owner"], ident) for row in rows for ident in row["receipt"].get("deleted_ids", [])}
    return [{"owner": owner, "draw_id": draw_id} for owner, draw_id in sorted(pairs)]


def _assert_owner(repo: Any, connection: Any, owner: str, draw_ids: list[str]) -> None:
    foreign = connection.execute(
        sql.SQL("SELECT 1 FROM {} WHERE id=ANY(%s) AND owner<>%s LIMIT 1").format(repo.table("tarot_draws")),
        (draw_ids, owner),
    ).fetchone()
    if foreign:
        raise ValueError("Deleted draw belongs to a different owner")
    foreign_marker = connection.execute(
        sql.SQL(
            "SELECT 1 FROM {} WHERE owner<>%s AND operation LIKE 'tarot-delete:%%' "
            "AND (receipt->'deleted_ids') ?| %s LIMIT 1"
        ).format(repo.table("core_mutation_requests")),
        (owner, draw_ids),
    ).fetchone()
    if foreign_marker:
        raise ValueError("Deleted draw tombstone belongs to a different owner")


def retain_deleted_draws(repo: Any, connection: Any, owner: str, draw_ids: Iterable[str]) -> int:
    """Call within apply's whole-export transaction and its current owner fence."""
    identifiers = sorted(set(draw_ids))
    if not identifiers:
        return 0
    repo.assert_scope(owner)
    _assert_owner(repo, connection, owner, identifiers)
    added = 0
    for draw_id in identifiers:
        key, payload, receipt = marker_identity(owner, draw_id)
        prior = connection.execute(
            sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND operation=%s AND request_key=%s").format(
                repo.table("core_mutation_requests")
            ),
            (owner, OPERATION, key),
        ).fetchone()
        observed = repo.mutation_request(owner, OPERATION, key, payload, lambda value=receipt: value)
        if observed != receipt:
            raise ValueError("Restored draw tombstone receipt conflicts with withdrawal")
        added += int(prior is None)
    return added

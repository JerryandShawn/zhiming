"""A trusted inbound opt-out fences later long-term effects of an existing run."""

from __future__ import annotations

from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.domain.contracts import EvidenceError


def block_thread_runs(repo: Any, owner: str, subject: str, thread: str, receipt: str) -> None:
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT id,usage FROM {} WHERE owner=%s AND subject=%s "
                "AND status IN ('queued','running','inbox_wait') "
                "AND coalesce(thread_id,request->>'thread_id','life:'||subject)=%s FOR UPDATE"
            ).format(repo.table("core_runs")),
            (owner, subject, thread),
        ).fetchall()
        for row in rows:
            _set_barrier(repo, connection, owner, row, thread, receipt)


def inherit_source_barrier(repo: Any, run: dict[str, Any], source_ids: list[str]) -> dict[str, Any]:
    """A delayed Feishu flush cannot save pre-opt-out originals by queuing later."""
    owner, subject = run["owner"], run["subject"]
    thread = run.get("thread_id") or run["request"].get("thread_id") or "life:" + subject
    with repo.transaction(owner) as connection:
        row = connection.execute(
            sql.SQL("SELECT id,status,usage FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(
                repo.table("core_runs")
            ),
            (owner, run["id"]),
        ).fetchone()
        if row["status"] not in {"queued", "running", "inbox_wait"}:
            return repo.fetch_run(owner, run["id"])
        receipt = connection.execute(
            sql.SQL(
                "SELECT r.id FROM {} r JOIN {} m ON m.owner=r.owner AND m.subject=r.subject "
                "AND m.kind='message' AND m.id=ANY(%s) AND m.created_at<=r.created_at "
                "WHERE r.owner=%s AND r.subject=%s AND r.kind='request' AND r.status='active' "
                "AND r.data->>'ingress'='privacy_route' AND r.data->>'blocks_current_run'='true' "
                "AND r.data->>'origin_thread_id'=%s ORDER BY r.created_at,r.id LIMIT 1"
            ).format(repo.table("core_entities"), repo.table("core_entities")),
            (source_ids, owner, subject, thread),
        ).fetchone()
        if receipt is not None:
            _set_barrier(repo, connection, owner, row, thread, receipt["id"])
        return repo.fetch_run(owner, run["id"])


def _set_barrier(repo: Any, connection: Any, owner: str, row: dict, thread: str, receipt: str) -> None:
    usage = dict(row["usage"] or {})
    usage["privacy_mode"] = {"blocked": True, "control_receipt": receipt, "thread_id": thread}
    connection.execute(
        sql.SQL("UPDATE {} SET usage=%s,updated_at=now() WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
        (Jsonb(usage), owner, row["id"]),
    )


def run_persistence_blocked(repo: Any, run: dict[str, Any]) -> bool:
    """Re-read PG authority; stale caller usage cannot reopen a stopped write gate."""
    current = repo.fetch_run(run["owner"], run["id"])
    if current["subject"] != run["subject"]:
        raise EvidenceError("隐私写入闸门的人物范围无效")
    barrier = (current.get("usage") or {}).get("privacy_mode")
    if barrier is None:
        return False
    if not isinstance(barrier, dict) or barrier.get("blocked") is not True:
        raise EvidenceError("隐私写入闸门元数据无效")
    receipt = repo.get(run["owner"], "request", barrier["control_receipt"])
    thread = current.get("thread_id") or current["request"].get("thread_id") or "life:" + current["subject"]
    if (
        receipt.get("ingress") != "privacy_route"
        or receipt.get("blocks_current_run") is not True
        or receipt["subject_id"] != current["subject"]
        or receipt.get("origin_thread_id") != thread
        or barrier.get("thread_id") != thread
    ):
        raise EvidenceError("隐私写入闸门缺少受信入站证明")
    return True

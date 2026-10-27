"""Frozen event rows and body-free operation metadata share the caller's transaction."""

from __future__ import annotations

import re
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.events import make_event, validate_event
from mingjing_core.domain.contracts import EvidenceError

from . import event_retention_metadata as retention
from .postgres import PostgresRepository, fingerprint

OPERATION_KIND = "run_event_v1"
PUBLIC_KEYS = {"v", "run_id", "seq", "ts"}


def _operation_id(run: dict[str, Any], key: str) -> str:
    if not isinstance(key, str) or re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", key) is None:
        raise EvidenceError("事件操作身份无效")
    epoch = run["retry_epoch"]
    if type(epoch) is not int or epoch < 0:
        raise EvidenceError("事件批次无效")
    return f"p4-event:{run['id']}:e{epoch}:{key}"


def _fingerprint(run: dict[str, Any], kind: str, payload: dict[str, Any]) -> str:
    thread = run.get("thread_id") or run.get("request", {}).get("thread_id") or "life:" + run["subject"]
    return fingerprint([run["owner"], run["id"], run["subject"], thread, run["retry_epoch"], kind, payload])


def _prior(
    repo: PostgresRepository, connection: Any, run: dict[str, Any], kind: str, operation: str, digest: str
) -> dict[str, Any] | None:
    row = connection.execute(
        sql.SQL("SELECT fingerprint,kind,result_id FROM {} WHERE owner=%s AND operation_id=%s").format(
            repo.table("core_operations")
        ),
        (run["owner"], operation),
    ).fetchone()
    if row is None:
        return None
    if row["fingerprint"] != digest or row["kind"] != OPERATION_KIND or not row["result_id"].isdecimal():
        raise EvidenceError("事件操作与原记录冲突")
    seq = int(row["result_id"])
    if not 0 < seq < 2**63:
        raise EvidenceError("事件操作序号无效")
    stored = connection.execute(
        sql.SQL("SELECT kind,payload FROM {} WHERE owner=%s AND run_id=%s AND seq=%s").format(
            repo.table("core_run_events")
        ),
        (run["owner"], run["id"], seq),
    ).fetchone()
    if not stored or stored["kind"] != kind or not stored["payload"]:
        raise EvidenceError("事件原件缺失或已清除，不能重建")
    data = validate_event(kind, stored["payload"])
    payload = {key: value for key, value in data.items() if key not in PUBLIC_KEYS}
    if data["run_id"] != run["id"] or data["seq"] != seq or _fingerprint(run, kind, payload) != digest:
        raise EvidenceError("事件原件与操作证明不符")
    return {"type": kind, "data": data}


def append_event(
    repo: PostgresRepository,
    connection: Any,
    run: dict[str, Any],
    kind: str,
    payload: dict[str, Any],
    *,
    operation_key: str | None = None,
) -> dict[str, Any]:
    """Call only inside the authoritative owner/run transaction, after its write fences."""
    current = retention.locked_run(repo, connection, run["owner"], run["id"])
    if (
        current["retry_epoch"] != run["retry_epoch"]
        or current["subject"] != run["subject"]
        or retention.is_closed(current)
    ):
        raise EvidenceError("事件写入身份或保留状态已失效")
    owner, ident = run["owner"], run["id"]
    operation = _operation_id(run, operation_key) if operation_key is not None else None
    digest = _fingerprint(run, kind, payload)
    if operation is not None and (prior := _prior(repo, connection, run, kind, operation, digest)) is not None:
        return prior
    seq = retention.next_sequence(repo, connection, run)
    event = make_event(kind, ident, seq, payload)
    connection.execute(
        sql.SQL("INSERT INTO {}(owner,run_id,seq,kind,payload) VALUES(%s,%s,%s,%s,%s)").format(
            repo.table("core_run_events")
        ),
        (owner, ident, seq, kind, Jsonb(event["data"])),
    )
    if operation is not None:
        connection.execute(
            sql.SQL("INSERT INTO {}(owner,operation_id,fingerprint,kind,result_id) VALUES(%s,%s,%s,%s,%s)").format(
                repo.table("core_operations")
            ),
            (owner, operation, digest, OPERATION_KIND, str(seq)),
        )
    connection.execute("SELECT pg_notify('mj_run',%s)", (ident + ":" + str(seq),))
    return event

"""Lease-protected program time is operational metadata, not a memory revision."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.domain.contracts import EvidenceError

if TYPE_CHECKING:
    from .postgres import PostgresRepository


def _instant(value: str) -> str:
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return stamp.astimezone(UTC).isoformat()
    except (TypeError, ValueError, OverflowError):
        raise EvidenceError("程序时间元数据无效") from None


def program_time(repo: PostgresRepository, owner: str, run: dict[str, Any], at: str, *, write: bool = True) -> str:
    at = _instant(at)
    with repo.transaction(owner) as connection:
        authoritative = repo._leased(connection, owner, run["id"], run["lease_token"])
        epoch = authoritative["retry_epoch"]
        if run.get("retry_epoch", 0) != epoch:
            raise EvidenceError("程序时间不属于当前运行批次")
        ident = run["id"] + ":e" + str(epoch) + ":program_time"
        old = connection.execute(
            sql.SQL("SELECT status,subject,data FROM {} WHERE owner=%s AND kind='runtime_step' AND id=%s").format(
                repo.table("core_entities")
            ),
            (owner, ident),
        ).fetchone()
        if old is not None:
            data = old["data"]
            if (
                old["status"] != "active"
                or old["subject"] != authoritative["subject"]
                or data.get("stage") != "program_time"
                or data.get("run_id") != run["id"]
                or set(data.get("output", {})) != {"at"}
            ):
                raise EvidenceError("程序时间元数据不可恢复")
            return _instant(data["output"]["at"])
        if not write:
            return at
        # This fixed, body-free row is not a memory edit. Normal entity put keeps
        # its usual revision/operation semantics; only this leased metadata skips it.
        data = {"run_id": run["id"], "stage": "program_time", "output": {"at": at}}
        connection.execute(
            sql.SQL("INSERT INTO {}(owner,kind,id,subject,data) VALUES(%s,'runtime_step',%s,%s,%s)").format(
                repo.table("core_entities")
            ),
            (owner, ident, authoritative["subject"], Jsonb(data)),
        )
        return at

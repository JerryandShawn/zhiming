"""Body-free, run-bound retention evidence; callers hold the authoritative run lock."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock

KEY = "event_retention_v1"
KIND = "run_event_retention_v1"
TERMINAL = {"succeeded", "failed", "stale", "cancelled", "revoked"}
STATE_KEYS = {"v", "high_watermark", "terminal", "closed", "cleanup_complete", "proof"}
ANCHOR_KEYS = {"at", "epoch", "attempts", "status"}
TOMBSTONE_KEYS = {
    "v",
    "run_hash",
    "seq",
    "kind",
    "epoch",
    "attempts",
    "deleted_at",
    "expires_at",
}


def instant(value: Any) -> datetime:
    try:
        stamp = datetime.fromisoformat(value) if isinstance(value, str) else None
        if stamp is not None and stamp.tzinfo is not None and stamp.utcoffset() is not None:
            return stamp
    except (ValueError, TypeError, OverflowError):
        pass
    raise EvidenceError("事件保留时间证明无效")


def run_hash(run: dict[str, Any]) -> str:
    return fingerprint([run["owner"], run["id"], run["subject"], run.get("thread_id")])


def now() -> datetime:
    return instant(get_clock().now().isoformat()).astimezone(UTC)


def namespace(run: dict[str, Any]) -> str:
    return "p4-retained:" + run_hash(run) + ":"


def _anchor(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.keys() != ANCHOR_KEYS
        or not isinstance(value["status"], str)
        or value["status"] not in TERMINAL
        or any(type(value[name]) is not int or value[name] < 0 for name in ("epoch", "attempts"))
    ):
        raise EvidenceError("事件终态证明无效")
    if instant(value["at"]).astimezone(UTC).isoformat() != value["at"]:
        raise EvidenceError("事件终态时间格式无效")
    return value


def state(run: dict[str, Any]) -> dict[str, Any] | None:
    value = run.get("usage", {}).get(KEY)
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or set(value) - STATE_KEYS
        or type(value.get("v")) is not int
        or value["v"] != 1
        or type(value.get("high_watermark")) is not int
        or not 0 <= value["high_watermark"] < 2**63
        or type(value.get("cleanup_complete")) is not bool
    ):
        raise EvidenceError("事件保留元数据无效")
    for name in ("terminal", "closed"):
        if name in value:
            _anchor(value[name])
    plain = {key: item for key, item in value.items() if key != "proof"}
    if value.get("proof") != fingerprint([KEY, run_hash(run), plain]):
        raise EvidenceError("事件保留证明与运行身份不符")
    return dict(value)


def locked_run(repo: Any, connection: Any, owner: str, ident: str) -> dict[str, Any]:
    row = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(repo.table("core_runs")),
        (owner, ident),
    ).fetchone()
    return repo._run(row)


def actual_maximum(repo: Any, connection: Any, run: dict[str, Any]) -> int:
    return _initial(repo, connection, run)["high_watermark"]


def _initial(repo: Any, connection: Any, run: dict[str, Any]) -> dict[str, Any]:
    maximum = connection.execute(
        sql.SQL("SELECT coalesce(max(seq),0) AS n FROM {} WHERE owner=%s AND run_id=%s").format(
            repo.table("core_run_events")
        ),
        (run["owner"], run["id"]),
    ).fetchone()["n"]
    return {"v": 1, "high_watermark": maximum, "cleanup_complete": False}


def store(repo: Any, connection: Any, run: dict[str, Any], value: dict[str, Any]) -> None:
    plain = {key: item for key, item in value.items() if key != "proof"}
    usage = dict(
        run["usage"],
        **{KEY: dict(plain, proof=fingerprint([KEY, run_hash(run), plain]))},
    )
    connection.execute(
        sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
        (Jsonb(usage), run["owner"], run["id"]),
    )
    run["usage"] = usage


def is_closed(run: dict[str, Any]) -> bool:
    value = state(run)
    closed = (value or {}).get("closed")
    return bool(
        closed
        and run["status"] in TERMINAL
        and closed["epoch"] == run["retry_epoch"]
        and closed["attempts"] == run["attempts"]
    )


def terminal_anchor(run: dict[str, Any]) -> dict[str, Any] | None:
    anchor = (state(run) or {}).get("terminal")
    if anchor and all(
        anchor[name] == run[field]
        for name, field in (
            ("epoch", "retry_epoch"),
            ("attempts", "attempts"),
            ("status", "status"),
        )
    ):
        return anchor
    return None


def record_terminal(repo: Any, connection: Any, owner: str, ident: str, *, at: datetime | None = None) -> None:
    run = locked_run(repo, connection, owner, ident)
    if run["runtime"] != "v4" or run["status"] not in TERMINAL or is_closed(run):
        return
    value = state(run) or _initial(repo, connection, run)
    if terminal_anchor(run) is not None:
        return
    value["terminal"] = {
        "at": (instant(at.isoformat()).astimezone(UTC) if at is not None else now()).isoformat(),
        "epoch": run["retry_epoch"],
        "attempts": run["attempts"],
        "status": run["status"],
    }
    value["cleanup_complete"] = False
    store(repo, connection, run, value)


def reopen_retry(repo: Any, connection: Any, owner: str, ident: str) -> None:
    run = locked_run(repo, connection, owner, ident)
    if run["runtime"] != "v4":
        return
    value = state(run) or _initial(repo, connection, run)
    value.pop("terminal", None)
    value.pop("closed", None)
    value["cleanup_complete"] = False
    store(repo, connection, run, value)


def next_sequence(repo: Any, connection: Any, expected: dict[str, Any]) -> int:
    run = locked_run(repo, connection, expected["owner"], expected["id"])
    if run["subject"] != expected["subject"] or run["retry_epoch"] != expected["retry_epoch"] or is_closed(run):
        raise EvidenceError("事件写入身份或保留状态已失效")
    actual = _initial(repo, connection, run)["high_watermark"]
    value = state(run) or {"v": 1, "high_watermark": actual, "cleanup_complete": False}
    seq = max(actual, value["high_watermark"]) + 1
    if seq >= 2**63:
        raise EvidenceError("事件序号已耗尽")
    value["high_watermark"] = seq
    store(repo, connection, run, value)
    return seq


def _decode(run: dict[str, Any], row: dict[str, Any], seq: int) -> dict[str, Any]:
    try:
        raw = row["result_id"]
        value = json.loads(raw) if isinstance(raw, str) and len(raw) <= 2048 else None
    except (ValueError, TypeError, RecursionError):
        value = None
    if (
        not isinstance(value, dict)
        or value.keys() != TOMBSTONE_KEYS
        or type(value["v"]) is not int
        or value["v"] != 1
        or value["run_hash"] != run_hash(run)
        or type(value["seq"]) is not int
        or value["seq"] != seq
        or not 0 < seq < 2**63
        or value["kind"] != "text_delta"
        or row["kind"] != KIND
        or any(type(value[name]) is not int or value[name] < 0 for name in ("epoch", "attempts"))
        or row["fingerprint"] != fingerprint([KIND, value])
        or raw != json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    ):
        raise EvidenceError("事件删除证明与当前运行不符")
    if instant(value["deleted_at"]) >= instant(value["expires_at"]):
        raise EvidenceError("事件删除证明时间无效")
    return value


def removed_cursor(repo: Any, connection: Any, run: dict[str, Any], seq: int) -> bool:
    row = connection.execute(
        sql.SQL("SELECT kind,fingerprint,result_id FROM {} WHERE owner=%s AND operation_id=%s").format(
            repo.table("core_operations")
        ),
        (run["owner"], namespace(run) + str(seq)),
    ).fetchone()
    if row is None:
        return False
    value = _decode(run, row, seq)
    return now() < instant(value["expires_at"])


def attest_deleted(repo: Any, connection: Any, run: dict[str, Any], row: dict[str, Any], anchor: dict) -> None:
    actual = connection.execute(
        sql.SQL(
            "SELECT kind,payload!='{{}}'::jsonb AS has_body FROM {} WHERE owner=%s AND run_id=%s AND seq=%s FOR UPDATE"
        ).format(repo.table("core_run_events")),
        (run["owner"], run["id"], row["seq"]),
    ).fetchone()
    if not actual or actual["kind"] != "text_delta" or not actual["has_body"] or row["kind"] != actual["kind"]:
        raise EvidenceError("事件清理缺少实际正文行")
    previous = connection.execute(
        sql.SQL("SELECT kind,fingerprint,result_id FROM {} WHERE owner=%s AND operation_id=%s FOR UPDATE").format(
            repo.table("core_operations")
        ),
        (run["owner"], namespace(run) + str(row["seq"])),
    ).fetchone()
    if previous is not None:
        _decode(run, previous, row["seq"])
        raise EvidenceError("已有删除证明不能与重新出现的正文混用")
    value = {
        "v": 1,
        "run_hash": run_hash(run),
        "seq": row["seq"],
        "kind": row["kind"],
        "epoch": anchor["epoch"],
        "attempts": anchor["attempts"],
        "deleted_at": now().isoformat(),
        "expires_at": (instant(anchor["at"]) + timedelta(days=30)).isoformat(),
    }
    connection.execute(
        sql.SQL("INSERT INTO {}(owner,operation_id,fingerprint,kind,result_id) VALUES(%s,%s,%s,%s,%s)").format(
            repo.table("core_operations")
        ),
        (
            run["owner"],
            namespace(run) + str(row["seq"]),
            fingerprint([KIND, value]),
            KIND,
            json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        ),
    )


def prune_tombstones(repo: Any, connection: Any, run: dict[str, Any], limit: int) -> int:
    prefix = namespace(run)
    rows = connection.execute(
        sql.SQL(
            "SELECT operation_id,kind,fingerprint,result_id FROM {} WHERE owner=%s AND kind=%s "
            "AND left(operation_id,%s)=%s ORDER BY operation_id LIMIT %s FOR UPDATE"
        ).format(repo.table("core_operations")),
        (run["owner"], KIND, len(prefix), prefix, limit),
    ).fetchall()
    for row in rows:
        suffix = row["operation_id"][len(prefix) :]
        if not 1 <= len(suffix) <= 19 or not suffix.isascii() or not suffix.isdecimal() or str(int(suffix)) != suffix:
            raise EvidenceError("事件删除操作身份无效")
        _decode(run, row, int(suffix))
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner=%s AND operation_id=%s AND kind=%s").format(
                repo.table("core_operations")
            ),
            (run["owner"], row["operation_id"], KIND),
        )
    return len(rows)

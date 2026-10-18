"""Lease-fenced v4 step storage; callers replay tools with the stable operation ID."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.domain.json_values import ensure_finite_json
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import Clock, get_clock

if TYPE_CHECKING:
    from psycopg import Connection

    from mingjing_core.repositories.postgres import PostgresRepository


def _json_object(value: object) -> dict[str, Any]:
    valid = isinstance(value, dict)
    if valid:
        try:
            ensure_finite_json(value)
            result = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError, RecursionError):
            valid = False
    if not valid:
        raise EvidenceError("步骤数据必须是有效JSON对象")
    return result


def input_fingerprint(kind: str, name: str, inputs: dict[str, Any]) -> str:
    """Include canonical arguments and the caller's effective source versions in inputs."""
    return fingerprint({"kind": kind, "name": name, "inputs": _json_object(inputs)})


def _same_json(left: Any, right: Any) -> bool:
    # Python equates True with 1; JSON booleans must not acknowledge a changed receipt.
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same_json(value, right[key]) for key, value in left.items())
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same_json(a, b) for a, b in zip(left, right, strict=True))
    return left == right


@dataclass(frozen=True)
class JournalStep:
    owner: str
    run_id: str
    subject: str
    epoch: int
    seq: int
    kind: str
    name: str
    input_fp: str
    status: str
    lease_token: str = field(repr=False)
    output: dict[str, Any] | None = field(repr=False)
    usage: dict[str, Any] = field(repr=False)
    started_at: datetime
    finished_at: datetime | None

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    @property
    def operation_id(self) -> str:
        return f"run:{self.run_id}:e{self.epoch}:s{self.seq}"


class Journal:
    """Create a fresh traversal for each execution/reclaim and replay from sequence one.

    This module never executes or charges a model/tool. No transaction spans external
    work. Tool effects must use mutation_request/application-service idempotency.
    """

    def __init__(self, repo: PostgresRepository, owner: str, *, clock: Clock | None = None) -> None:
        if not isinstance(owner, str) or not owner.strip() or len(owner) > 200:
            raise ScopeError("步骤日志需要明确身份")
        self.repo, self.owner, self.clock = repo, owner, clock or get_clock()
        self._cursors: dict[tuple[str, int], int] = {}
        self._lock = threading.Lock()

    def _now(self) -> datetime:
        value = self.clock.now()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise EvidenceError("步骤日志时钟无效")
        return value.astimezone(UTC)

    def _leased(self, connection: Connection[Any], run: Mapping[str, Any]) -> dict[str, Any]:
        if run.get("owner") != self.owner or run.get("owner_user_id", self.owner) != self.owner:
            raise ScopeError("运行不属于当前身份")
        epoch, ident, token = run.get("retry_epoch"), run.get("id"), run.get("lease_token")
        if type(epoch) is not int or epoch < 0 or not isinstance(ident, str) or not isinstance(token, str):
            raise EvidenceError("步骤运行身份无效")
        row = self.repo._leased(connection, self.owner, ident, token)
        if row["retry_epoch"] != epoch:
            raise LeaseConflict("步骤不属于当前运行批次")
        if row["subject"] != run.get("subject") or run.get("subject_id", row["subject"]) != row["subject"]:
            raise ScopeError("步骤人物范围不符")
        self.repo.assert_scope(self.owner, row["subject"])
        if row["runtime"] != "v4":
            raise EvidenceError("步骤日志仅用于v4运行")
        if row["cancel_requested_at"] is not None:
            raise LeaseConflict("本轮已请求停止")
        if row["deadline_at"] is not None and row["deadline_at"] <= self._now():
            raise LeaseConflict("本轮执行时间已结束")
        return row

    @staticmethod
    def _validate_identity(kind: str, name: str, input_fp: str) -> None:
        if kind not in {"model", "tool"} or not isinstance(name, str):
            raise EvidenceError("步骤类型无效")
        if (kind == "tool" or name) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,79}", name) is None:
            raise EvidenceError("步骤名称无效")
        if not isinstance(input_fp, str) or re.fullmatch(r"[0-9a-f]{64}", input_fp) is None:
            raise EvidenceError("步骤输入指纹无效")

    def _read(self, connection: Connection[Any], run_id: str, epoch: int, seq: int) -> dict[str, Any] | None:
        return connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s FOR UPDATE").format(
                self.repo.table("core_run_steps")
            ),
            (self.owner, run_id, epoch, seq),
        ).fetchone()

    @staticmethod
    def _check(row: dict[str, Any], kind: str, name: str, input_fp: str) -> None:
        if (row["kind"], row["name"], row["input_fp"]) != (kind, name, input_fp):
            raise EvidenceError("步骤身份或输入与持久记录冲突")
        if row["error_code"] or row["status"] not in {"started", "completed"}:
            raise EvidenceError("步骤正文已失效，不能恢复")
        if row["status"] == "completed" and (not isinstance(row["output"], dict) or row["finished_at"] is None):
            raise EvidenceError("步骤完成记录缺失，不能恢复")

    def _step(self, row: dict[str, Any], run: Mapping[str, Any]) -> JournalStep:
        return JournalStep(
            self.owner,
            row["run_id"],
            run["subject"],
            row["epoch"],
            row["seq"],
            row["kind"],
            row["name"],
            row["input_fp"],
            row["status"],
            run["lease_token"],
            row["output"],
            row["usage"],
            row["started_at"],
            row["finished_at"],
        )

    def next_or_replay(self, run: Mapping[str, Any], *, kind: str, input_fp: str, name: str = "") -> JournalStep:
        self._validate_identity(kind, name, input_fp)
        with self._lock:
            with self.repo.transaction(self.owner) as connection:
                current = self._leased(connection, run)
                key = current["id"], current["retry_epoch"]
                seq = self._cursors.get(key, 1)
                row = self._read(connection, *key, seq)
                if row is None:
                    row = connection.execute(
                        sql.SQL(
                            "INSERT INTO {}(owner,run_id,epoch,seq,kind,name,status,input_fp,started_at) "
                            "VALUES(%s,%s,%s,%s,%s,%s,'started',%s,%s) RETURNING *"
                        ).format(self.repo.table("core_run_steps")),
                        (self.owner, *key, seq, kind, name, input_fp, self._now()),
                    ).fetchone()
                self._check(row, kind, name, input_fp)
                result = self._step(row, current)
            self._cursors[key] = seq + 1
        return result

    def complete(self, step: JournalStep, output: dict[str, Any], usage: dict[str, Any] | None = None) -> JournalStep:
        output, usage = _json_object(output), _json_object({} if usage is None else usage)
        if step.owner != self.owner or type(step.seq) is not int or step.seq < 1:
            raise ScopeError("步骤不属于当前身份")
        self._validate_identity(step.kind, step.name, step.input_fp)
        run = {
            "id": step.run_id,
            "owner": step.owner,
            "subject": step.subject,
            "retry_epoch": step.epoch,
            "lease_token": step.lease_token,
        }
        with self.repo.transaction(self.owner) as connection:
            current = self._leased(connection, run)
            row = self._read(connection, step.run_id, step.epoch, step.seq)
            if row is None:
                raise EvidenceError("步骤尚未开始，不能完成")
            self._check(row, step.kind, step.name, step.input_fp)
            if row["status"] == "completed":
                if not _same_json(row["output"], output) or not _same_json(row["usage"], usage):
                    raise EvidenceError("已完成步骤不能用不同结果覆盖")
                return self._step(row, current)
            finished_at = self._now()
            if finished_at < row["started_at"]:
                raise EvidenceError("步骤完成时间早于开始时间")
            row = connection.execute(
                sql.SQL(
                    "UPDATE {} SET status='completed',output=%s,usage=%s,finished_at=%s "
                    "WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s RETURNING *"
                ).format(self.repo.table("core_run_steps")),
                (Jsonb(output), Jsonb(usage), finished_at, self.owner, step.run_id, step.epoch, step.seq),
            ).fetchone()
            return self._step(row, current)

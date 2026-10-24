"""Private event identities; public payloads remain in the native event table only."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from mingjing_core.agent.events import validate_event
from mingjing_core.agent.journal import Journal, JournalStep
from mingjing_core.application.agent_commit_versions import reconcile_versions
from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.public_tool_ids import public_call_id
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

KEY = "runtime_event_receipts"
SCHEMA = "journal-public-events-v1"
TOOLS = {"tool_call", "tool_result"}
HASH = re.compile(r"[0-9a-f]{64}")
TOOL_KEY = re.compile(r"e(0|[1-9][0-9]*):s([1-9][0-9]*):(tool_call|tool_result)")


class EventReceipts:
    def __init__(self, repo: PostgresRepository, run: dict[str, Any]) -> None:
        self.repo, self.run = repo, run

    def _authority(self, connection: Any) -> dict[str, Any]:
        # This also checks the actual source/thread, cancellation and deadline.
        row = AgentSnapshotStore(self.repo)._authority(connection, self.run)
        if not self.repo.verify_versions(row["owner"], row["state_version"]):
            versions = reconcile_versions(self.repo, row, row["state_version"])
            if not self.repo.verify_versions(row["owner"], versions):
                raise EvidenceError("公开事件的实际采用来源已经变化")
            self.repo.set_run_dependencies(row["owner"], row["id"], versions, row["lease_token"])
            row["state_version"] = versions
        return row

    def _state(self, connection: Any, row: dict) -> tuple[dict, bool]:
        if not isinstance(row["usage"], dict):
            raise EvidenceError("公开事件运行元数据无效")
        value = row["usage"].get(KEY)
        legacy = KEY not in row["usage"]
        if legacy:
            value = {"schema": SCHEMA, "epochs": {}, "receipts": {}}
        if (
            not isinstance(value, dict)
            or set(value) != {"schema", "epochs", "receipts"}
            or value["schema"] != SCHEMA
            or not isinstance(value["epochs"], dict)
            or not isinstance(value["receipts"], dict)
        ):
            raise EvidenceError("公开事件私密协议损坏")
        if not legacy and "started" not in value["receipts"]:
            raise EvidenceError("原公开事件协议缺少开始收据，不能重建")
        for epoch, schema in value["epochs"].items():
            if (
                not isinstance(epoch, str)
                or re.fullmatch(r"0|[1-9][0-9]*", epoch) is None
                or int(epoch) > row["retry_epoch"]
                or schema != SCHEMA
            ):
                raise EvidenceError("公开事件协议批次无效")
        acknowledged, sequences = set(), set()
        for key, receipt in value["receipts"].items():
            match = TOOL_KEY.fullmatch(key) if isinstance(key, str) else None
            if key != "started" and (match is None or match[1] not in value["epochs"]):
                raise EvidenceError("公开事件收据步骤无效")
            if (
                not isinstance(receipt, dict)
                or set(receipt) != {"identity_sha256", "event_seq", "event_sha256"}
                or type(receipt["event_seq"]) is not int
                or receipt["event_seq"] < 1
                or any(
                    not isinstance(receipt[name], str) or HASH.fullmatch(receipt[name]) is None
                    for name in ("identity_sha256", "event_sha256")
                )
            ):
                raise EvidenceError("公开事件收据损坏")
            if match:
                acknowledged.add((receipt["event_seq"], match[3]))
            if receipt["event_seq"] in sequences:
                raise EvidenceError("公开事件收据不能共用序号")
            sequences.add(receipt["event_seq"])
        old = connection.execute(
            sql.SQL(
                "SELECT seq,kind FROM {} WHERE owner=%s AND run_id=%s AND kind IN ('tool_call','tool_result')"
            ).format(self.repo.table("core_run_events")),
            (row["owner"], row["id"]),
        ).fetchall()
        if any((event["seq"], event["kind"]) not in acknowledged for event in old):
            raise EvidenceError("旧工具事件缺少原生收据，不能猜测所属步骤")
        present = {(event["seq"], event["kind"]) for event in old}
        for key, receipt in value["receipts"].items():
            match = TOOL_KEY.fullmatch(key)
            if match and int(match[1]) == row["retry_epoch"] and (receipt["event_seq"], match[3]) not in present:
                raise EvidenceError("当前批次的原公开工具事件缺失")
        return value, legacy

    def _save(self, connection: Any, row: dict, state: dict) -> None:
        # All callers still hold the real run lock; never merge a caller snapshot.
        usage = dict(row["usage"], **{KEY: state})
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(self.repo.table("core_runs")),
            (Jsonb(usage), row["owner"], row["id"]),
        )

    def begin_epoch(self, connection: Any) -> None:
        row = self._authority(connection)
        state, legacy = self._state(connection, row)
        if legacy or "started" not in state["receipts"]:
            raise EvidenceError("内部重新生成缺少原公开事件协议")
        if str(row["retry_epoch"]) not in state["epochs"]:
            state = self._new_epoch(connection, row, state)
            self._save(connection, row, state)

    def _new_epoch(self, connection: Any, row: dict, state: dict) -> dict:
        exists = connection.execute(
            sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s LIMIT 1").format(
                self.repo.table("core_run_steps")
            ),
            (row["owner"], row["id"], row["retry_epoch"]),
        ).fetchone()
        if exists:
            raise EvidenceError("已有步骤却缺少原公开事件协议")
        return dict(state, epochs=dict(state["epochs"], **{str(row["retry_epoch"]): SCHEMA}))

    def _read(self, connection: Any, row: dict, seq: int, kind: str, payload: dict) -> dict:
        old = connection.execute(
            sql.SQL("SELECT seq,kind,payload FROM {} WHERE owner=%s AND run_id=%s AND seq=%s").format(
                self.repo.table("core_run_events")
            ),
            (row["owner"], row["id"], seq),
        ).fetchone()
        if old is None or old["kind"] != kind:
            raise EvidenceError("原公开事件缺失，不能重建")
        value = validate_event(kind, old["payload"])
        body = {key: child for key, child in value.items() if key not in {"v", "run_id", "seq", "ts"}}
        if value["run_id"] != row["id"] or value["seq"] != seq or fingerprint(body) != fingerprint(payload):
            raise EvidenceError("原公开事件与实际步骤不符")
        return {"type": kind, "data": value}

    def _event(
        self,
        connection: Any,
        row: dict,
        state: dict,
        key: str,
        identity: dict,
        kind: str,
        payload: dict,
        append: Callable[[Any, str, dict], dict],
        *,
        legacy: bool = False,
    ) -> dict:
        receipt = state["receipts"].get(key)
        digest = fingerprint(identity)
        if receipt is not None:
            if receipt["identity_sha256"] != digest:
                raise EvidenceError("原公开事件步骤身份改变")
            event = self._read(connection, row, receipt["event_seq"], kind, payload)
            if fingerprint(event) != receipt["event_sha256"]:
                raise EvidenceError("原公开事件摘要改变")
            if state != row["usage"].get(KEY):
                self._save(connection, row, state)
            return event
        old = []
        if kind == "started":
            old = connection.execute(
                sql.SQL("SELECT seq FROM {} WHERE owner=%s AND run_id=%s AND kind='started' ORDER BY seq").format(
                    self.repo.table("core_run_events")
                ),
                (row["owner"], row["id"]),
            ).fetchall()
            if old and (not legacy or len(old) != 1):
                raise EvidenceError("原开始事件缺少唯一可信收据")
        event = self._read(connection, row, old[0]["seq"], kind, payload) if old else append(connection, kind, payload)
        receipt = dict(identity_sha256=digest, event_seq=event["data"]["seq"], event_sha256=fingerprint(event))
        state = dict(state, receipts=dict(state["receipts"], **{key: receipt}))
        self._save(connection, row, state)
        return event

    def started(self, connection: Any, payload: dict, append: Callable[[Any, str, dict], dict]) -> dict:
        row = self._authority(connection)
        state, legacy = self._state(connection, row)
        epoch = str(row["retry_epoch"])
        if epoch not in state["epochs"]:
            state = self._new_epoch(connection, row, state)
        identity = {key: row[key] for key in ("owner", "id", "subject")}
        return self._event(connection, row, state, "started", identity, "started", payload, append, legacy=legacy)

    def _step(self, connection: Any, row: dict, step: JournalStep, kind: str) -> tuple[dict, dict]:
        if (
            type(step) is not JournalStep
            or type(step.seq) is not int
            or step.seq < 1
            or type(step.epoch) is not int
            or step.epoch < 0
            or (step.owner, step.run_id, step.subject, step.epoch, step.lease_token)
            != (row["owner"], row["id"], row["subject"], row["retry_epoch"], row["lease_token"])
        ):
            raise EvidenceError("工具事件不属于当前受信步骤")
        journal = Journal(self.repo, row["owner"])
        journal._leased(connection, self.run)
        journal._validate_identity(step.kind, step.name, step.input_fp)
        actual = journal._read(connection, step.run_id, step.epoch, step.seq)
        if actual is None or step.kind != "tool" or actual["started_at"] != step.started_at:
            raise EvidenceError("工具事件缺少实际Journal")
        journal._check(actual, step.kind, step.name, step.input_fp)
        identity = {key: actual[key] for key in ("owner", "run_id", "epoch", "seq", "kind", "name", "input_fp")}
        identity.update(subject=row["subject"], started_at=actual["started_at"].astimezone(UTC).isoformat())
        if kind == "tool_result":
            if actual["status"] != "completed":
                raise EvidenceError("工具结果事件缺少实际完成步骤")
            identity.update(
                output_sha256=fingerprint(actual["output"]),
                finished_at=actual["finished_at"].astimezone(UTC).isoformat(),
            )
        return actual, identity

    def tool(
        self,
        connection: Any,
        step: JournalStep,
        kind: str,
        payload: dict,
        append: Callable[[Any, str, dict], dict],
    ) -> dict:
        # Only LoopCycle supplies the fixed safe payload. This is storage lineage,
        # not an independent public/caller authorization to execute a tool.
        if kind not in TOOLS:
            raise EvidenceError("未知Journal工具事件")
        row = self._authority(connection)
        actual, identity = self._step(connection, row, step, kind)
        state, _ = self._state(connection, row)
        if str(row["retry_epoch"]) not in state["epochs"]:
            raise EvidenceError("工具步骤缺少原公开事件协议")
        fields = {"call_id", "name", "summary"} | ({"ok"} if kind == "tool_result" else set())
        if set(payload) != fields or payload["name"] != actual["name"]:
            raise EvidenceError("工具事件超出安全字段")
        summary = "正在处理这一步"
        if kind == "tool_result":
            try:
                result = ToolResult.model_validate(actual["output"])
            except ValidationError:
                raise EvidenceError("工具完成结果不能验证") from None
            if type(payload["ok"]) is not bool or payload["ok"] != result.ok:
                raise EvidenceError("工具事件与实际结果不符")
            summary = (
                "算了一下日期"
                if step.name == "date_calc" and result.ok
                else ("已完成" if result.ok else "这一步尚未完成")
            )
        if payload["summary"] != summary:
            raise EvidenceError("工具事件摘要不是固定安全文案")
        payload = dict(payload, call_id=public_call_id(row, payload["call_id"]))
        key = f"e{step.epoch}:s{step.seq}:{kind}"
        return self._event(connection, row, state, key, identity, kind, payload, append)

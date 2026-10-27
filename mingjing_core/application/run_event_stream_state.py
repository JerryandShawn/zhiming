"""Actual journal/request proof fences persistent candidate stream generations and offsets."""

from __future__ import annotations

import hashlib
import re
import threading
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.journal import Journal, JournalStep
from mingjing_core.application.agent_crisis_sources import turn_sources
from mingjing_core.application.agent_current_sources import current_source_ids
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_thread_scope import assert_thread, thread_id
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.repositories.run_event_log import append_event
from mingjing_core.repositories.streaming_transaction import streaming_transaction

STATE_KEY = "p4_stream_candidate"
STATE_FIELDS = {"schema", "epoch", "seq", "input_fp", "lease_sha256", "generation", "received", "emitted", "closed"}


def stream_metadata(run: dict[str, Any]) -> dict[str, Any] | None:
    value = run["usage"].get(STATE_KEY)
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != STATE_FIELDS or value["schema"] != "p4-stream-state-v1":
        raise EvidenceError("流式生成元数据无效")
    if any(
        type(value[key]) is not int or value[key] < 0 for key in ("epoch", "seq", "generation", "received", "emitted")
    ):
        raise EvidenceError("流式生成计数无效")
    if type(value["closed"]) is not bool or min(value["seq"], value["generation"]) < 1:
        raise EvidenceError("流式生成状态无效")
    if value["emitted"] > value["received"] or value["closed"] and value["emitted"] != value["received"]:
        raise EvidenceError("流式生成区间无效")
    if any(
        not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key])
        for key in ("input_fp", "lease_sha256")
    ):
        raise EvidenceError("流式生成指纹无效")
    return dict(value)


class StreamState:
    def __init__(self, repo: PostgresRepository, run: dict[str, Any], ledger: RequestLedger) -> None:
        self.repo, self.run, self.ledger = repo, dict(run), ledger

    def _proof(self, connection: Any, step: JournalStep) -> dict[str, Any]:
        run, journal = self.run, Journal(self.repo, self.run["owner"])
        current = self.repo._run(journal._leased(connection, run))
        if (step.owner, step.run_id, step.subject, step.epoch, step.lease_token) != (
            run["owner"],
            run["id"],
            run["subject"],
            run["retry_epoch"],
            run["lease_token"],
        ) or thread_id(current) != thread_id(run):
            raise LeaseConflict("流式步骤不属于当前运行范围")
        assert_thread(self.repo, current)
        row = journal._read(connection, step.run_id, step.epoch, step.seq)
        if not row or (row["kind"], row["name"], row["input_fp"], row["status"]) != (
            "model",
            "",
            step.input_fp,
            "started",
        ):
            raise EvidenceError("流式输出缺少真实进行中模型步骤")
        if row["output"] is not None or row["finished_at"] is not None or row["error_code"] is not None:
            raise EvidenceError("已完成或失效模型步骤不能开始流式输出")
        record = self.repo.get(run["owner"], "runtime_step", self.ledger._id(step.run_id, step.epoch, step.seq))
        prepared = self.ledger._load(run["owner"], step.run_id, step.epoch, step.seq)
        if record.get("input_fp") != step.input_fp or record["subject_id"] != step.subject:
            raise EvidenceError("流式步骤与原模型请求不符")
        if prepared is None or prepared.role != "primary" or prepared.name != "":
            raise EvidenceError("私有模型步骤不能公开流式正文")
        if not self.repo.verify_versions(run["owner"], prepared.versions):
            raise LeaseConflict("流式正文的原依赖版本已经改变")
        sources = turn_sources(self.repo, current, current_source_ids(self.repo, current))
        primary = next(row for row in sources if row["id"] == current["request"]["source_message_id"])
        if primary["content"] != current["request"]["message"]:
            raise EvidenceError("流式正文的本轮原话已经改变")
        return current

    def _save(self, connection: Any, run: dict[str, Any], metadata: dict[str, Any]) -> None:
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(self.repo.table("core_runs")),
            (Jsonb(dict(run["usage"], **{STATE_KEY: metadata})), run["owner"], run["id"]),
        )

    def begin(self, step: JournalStep, *, stopped: threading.Event | None = None) -> dict[str, Any]:
        with streaming_transaction(self.repo, self.run["owner"], stopped) as connection:
            current = self._proof(connection, step)
            previous = stream_metadata(current)
            if previous is not None and (
                not previous["closed"]
                or previous["epoch"] > step.epoch
                or previous["epoch"] == step.epoch
                and previous["seq"] >= step.seq
            ):
                raise EvidenceError("上一段流式尚未安全结束，恢复接线未启用")
            metadata = {
                "schema": "p4-stream-state-v1",
                "epoch": step.epoch,
                "seq": step.seq,
                "input_fp": step.input_fp,
                "lease_sha256": hashlib.sha256(step.lease_token.encode()).hexdigest(),
                "generation": previous["generation"] + 1 if previous else 1,
                "received": 0,
                "emitted": 0,
                "closed": False,
            }
            self._save(connection, current, metadata)
            return metadata

    def commit(
        self,
        step: JournalStep,
        expected: dict[str, Any],
        chunk: str,
        drafts: tuple[Any, ...],
        *,
        closed: bool = False,
        stopped: threading.Event | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if type(chunk) is not str or type(closed) is not bool:
            raise EvidenceError("流式正文或结束标记无效")
        with streaming_transaction(self.repo, self.run["owner"], stopped) as connection:
            current = self._proof(connection, step)
            actual = stream_metadata(current)
            if actual != expected or actual is None or actual["closed"]:
                raise LeaseConflict("流式生成版本已经改变")
            if (actual["epoch"], actual["seq"], actual["input_fp"]) != (step.epoch, step.seq, step.input_fp):
                raise LeaseConflict("流式生成不属于当前模型步骤")
            if actual["lease_sha256"] != hashlib.sha256(step.lease_token.encode()).hexdigest():
                raise LeaseConflict("流式生成租约已经改变")
            received, emitted, events = actual["received"] + len(chunk), actual["emitted"], []
            for draft in drafts:
                if draft.type != "text_delta":
                    raise EvidenceError("本流式接点仅接受正文分片")
                end = emitted + len(draft.payload["text"])
                if not emitted < end <= received:
                    raise EvidenceError("流式正文区间与真实接收计数不符")
                key = f"stream:s{step.seq}:g{actual['generation']}:chars:{emitted}:{end}"
                events.append(
                    append_event(self.repo, connection, current, "text_delta", dict(draft.payload), operation_key=key)
                )
                emitted = end
            if closed and emitted != received:
                raise EvidenceError("流式结束前尚有未持久正文")
            metadata = dict(actual, received=received, emitted=emitted, closed=closed)
            self._save(connection, current, metadata)
            return metadata, events

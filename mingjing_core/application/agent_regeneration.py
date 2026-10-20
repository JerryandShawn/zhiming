"""One clean epoch for newly withdrawn injected sources; never reuse private output."""

from __future__ import annotations

import hashlib
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.context_types import ContextBuild
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.thread_sources import ingress_sources, source_segments
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.dependencies import lineage_key
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import get_clock


def lease_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AgentRegenerator:
    def __init__(self, repo: PostgresRepository) -> None:
        self.repo = repo

    def _related(self, run: dict[str, Any], frozen: ContextBuild) -> bool:
        keys = {lineage_key(key) for key in frozen.injected_versions}
        for row in self.repo.revocations(run["owner"]):
            if row["revision"] <= frozen.snapshot_revision:
                continue
            if row["kind"] + ":" + row["entity_id"] in keys:
                return True
            if row["kind"] == "source_span" and "message:" + str(row["metadata"].get("message_id")) in keys:
                return True
        return False

    def _request(self, original: dict[str, Any]) -> dict[str, Any]:
        request = original["request"]
        if (original.get("thread_id") or "").startswith("incognito:") or any(
            request.get(key) for key in ("images", "draw_id", "reading_id", "selection", "parent_run", "incognito")
        ):
            raise EvidenceError("复杂输入撤销后需要明确的新请求，不能自动恢复旧私密输入")
        allowed = {
            "message",
            "source_message_id",
            "conversation_id",
            "case_ids",
            "mode",
            "depth",
            "selection",
            "draw_id",
            "images",
            "parent_run",
            "reading_id",
            "thread_id",
            "incognito",
            "area_id",
            "topic_id",
            "source_message_ids",
            "source_segments",
            "inbox_parent_run_id",
        }
        if set(request) - allowed:
            raise EvidenceError("未知输入不能在撤销后自动重建")
        source = self._primary(original)
        for ident in request.get("case_ids", []):
            case = self.repo.get(original["owner"], "case", ident)
            if case["subject_id"] != original["subject"]:
                raise EvidenceError("重新生成的事项范围不符")
        rebuilt = dict(request, message=source["content"], source_message_id=source["id"])
        if "source_message_ids" in request or "source_segments" in request:
            sources = self._remaining_sources(original)
            rebuilt.update(source_message_ids=[row["id"] for row in sources], source_segments=source_segments(sources))
        rebuilt.pop("inbox_parent_run_id", None)
        return rebuilt

    def _primary(self, original: dict[str, Any]) -> dict[str, Any]:
        request = original["request"]
        source = MemoryService(self.repo).get_source(original["owner"], request["source_message_id"])
        if (
            source["status"] != "active"
            or source["subject_id"] != original["subject"]
            or source.get("role") != "user"
            or source.get("content") != request["message"]
            or source.get("policy", {}).get("origin") != "current_user"
            or source.get("policy", {}).get("run_context") is not True
            or source.get("thread_id") != (original.get("thread_id") or "life:" + original["subject"])
        ):
            raise EvidenceError("当前用户原话已撤销或改变，不能重新生成")
        for row in self.repo.revocations(original["owner"]):
            if (
                row["kind"] == "message"
                and row["entity_id"] == source["id"]
                or (row["kind"] == "source_span" and row["metadata"].get("message_id") == source["id"])
            ):
                raise EvidenceError("当前用户原话已撤销，不能自动恢复")
        return source

    def _remaining_sources(self, original: dict[str, Any]) -> list[dict[str, Any]]:
        owner, subject, request = original["owner"], original["subject"], original["request"]
        identifiers, segments = request.get("source_message_ids"), request.get("source_segments")
        if (
            not isinstance(identifiers, list)
            or not 1 <= len(identifiers) <= 64
            or any(not isinstance(ident, str) for ident in identifiers)
            or len(set(identifiers)) != len(identifiers)
            or not isinstance(segments, list)
            or len(segments) != len(identifiers)
            or any(not isinstance(segment, dict) for segment in segments)
            or [segment.get("message_id") for segment in segments] != identifiers
            or identifiers[-1] != request["source_message_id"]
        ):
            raise EvidenceError("重新生成的合并来源或顺序无效")
        revocations = self.repo.revocations(owner)
        remaining = []
        for ident, segment in zip(identifiers, segments, strict=True):
            row = self.repo.get(owner, "message", ident, include_deleted=True)
            if row["subject_id"] != subject:
                raise ScopeError("重新生成不能迁移其他人物的原话")
            withdrawn = any(
                item["kind"] == "message"
                and item["entity_id"] == ident
                or item["kind"] == "source_span"
                and item["metadata"].get("message_id") == ident
                for item in revocations
            )
            if withdrawn:
                if ident == request["source_message_id"]:
                    raise EvidenceError("当前用户原话已撤销，不能自动恢复")
                continue
            actual = ingress_sources(self.repo, owner, subject, original["thread_id"], [ident])[0]
            if source_segments([actual]) != [segment]:
                raise EvidenceError("非撤销的原话版本或区间已改变，不能重置版本掩盖变化")
            remaining.append(actual)
        ordered = sorted(remaining, key=lambda item: (item["at_ms"], item["created_at"], item["id"]))
        if ordered != remaining or not ordered or ordered[-1]["id"] != request["source_message_id"]:
            raise EvidenceError("合并原话的当前顺序与原始主问题不符")
        return ordered

    def _proven_request(self, connection: Any, current: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
        request = original["request"]
        route_keys = {"thread_id", "incognito", "source_message_ids", "source_segments", "inbox_parent_run_id"}
        base = {key: value for key, value in request.items() if key not in route_keys}
        if (
            current["fingerprint"] != fingerprint([current["subject"], request.get("depth", "standard"), base])
            or original.get("fingerprint") != current["fingerprint"]
            or original.get("operation_id") != current["operation_id"]
            or original.get("thread_id") != current["thread_id"]
            or request.get("thread_id", current["thread_id"]) != current["thread_id"]
            or current["request"]
            and fingerprint(current["request"]) != fingerprint(request)
        ):
            raise EvidenceError("重新生成缺少原始持久请求证明")
        if "source_message_ids" in request or "source_segments" in request:
            self._merged_authority(connection, current, request)
        return dict(self.repo._run(current), request=request)

    def _merged_authority(self, connection: Any, current: dict[str, Any], request: dict[str, Any]) -> None:
        ident = "thread-inbox:" + current["id"]
        parent = request.get("inbox_parent_run_id")
        data = dict(
            ingress="thread_inbox",
            thread_id=current["thread_id"],
            fallback_run_id=current["id"],
            parent_run_id=parent,
            inbox_state="waiting" if parent else "queued",
            source_ids=request.get("source_message_ids"),
            source_segments=request.get("source_segments"),
            incognito=request.get("incognito"),
        )
        operation = connection.execute(
            sql.SQL("SELECT fingerprint,kind,result_id FROM {} WHERE owner=%s AND operation_id=%s").format(
                self.repo.table("core_operations")
            ),
            (current["owner"], ident),
        ).fetchone()
        if (
            operation is None
            or operation["kind"] != "request"
            or operation["result_id"] != ident
            or operation["fingerprint"] != fingerprint(["request", ident, current["subject"], None, data])
        ):
            raise EvidenceError("合并原话缺少原始入队区间的持久证明")

    def restart(self, original: dict[str, Any], frozen: ContextBuild) -> dict[str, Any]:
        owner, ident = original["owner"], original["id"]
        with self.repo.transaction(owner) as connection:
            row = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(self.repo.table("core_runs")),
                (owner, ident),
            ).fetchone()
            if not row or row["runtime"] != "v4" or row["subject"] != original["subject"] or row["retry_epoch"] != 0:
                raise EvidenceError("本轮只能在原人物范围内重新生成一次")
            meta = row["usage"].get("agent_runtime", {})
            if meta.get("executor_lease_sha256") != lease_hash(original["lease_token"]) or meta.get("regenerations", 0):
                raise LeaseConflict("重新生成缺少本次受信执行凭据")
            if (
                row["cancel_requested_at"] is not None
                or row["status"] not in {"running", "stale", "revoked"}
                or row["deadline_at"] is not None
                and row["deadline_at"] <= get_clock().now()
            ):
                raise LeaseConflict("当前运行已经停止或过期")
            if row["status"] == "running" and row["lease_token"] != original["lease_token"]:
                raise LeaseConflict("重新生成的租约已经被替换")
            if not self._related(original, frozen):
                raise EvidenceError("没有与本轮采用来源相关的新撤销，不自动重新生成")
            proven = self._proven_request(connection, row, original)
            request = self._request(proven)
            usage = dict(row["usage"], agent_runtime=dict(meta, regenerations=1))
            connection.execute(
                sql.SQL("UPDATE {} SET status='stale',request=%s,usage=%s WHERE owner=%s AND id=%s").format(
                    self.repo.table("core_runs")
                ),
                (Jsonb(request), Jsonb(usage), owner, ident),
            )
            self.repo.prepare_retry(owner, ident)
            return self.repo.claim_run(owner, ident, lease_seconds=150)

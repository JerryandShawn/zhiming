"""One clean epoch for newly withdrawn injected sources; never reuse private output."""

from __future__ import annotations

import hashlib
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.context_types import ContextBuild
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict
from mingjing_core.repositories.dependencies import lineage_key
from mingjing_core.repositories.postgres import PostgresRepository
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
        if any(request.get(key) for key in ("images", "draw_id", "reading_id", "selection", "parent_run", "incognito")):
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
        }
        if set(request) - allowed:
            raise EvidenceError("未知输入不能在撤销后自动重建")
        source = MemoryService(self.repo).get_source(original["owner"], request["source_message_id"])
        if (
            source["status"] != "active"
            or source["subject_id"] != original["subject"]
            or source.get("role") != "user"
            or source.get("content") != request["message"]
            or source.get("policy", {}).get("origin") != "current_user"
            or source.get("policy", {}).get("run_context") is not True
        ):
            raise EvidenceError("当前用户原话已撤销或改变，不能重新生成")
        for row in self.repo.revocations(original["owner"]):
            if (
                row["kind"] == "message"
                and row["entity_id"] == source["id"]
                or (row["kind"] == "source_span" and row["metadata"].get("message_id") == source["id"])
            ):
                raise EvidenceError("当前用户原话已撤销，不能自动恢复")
        for ident in request.get("case_ids", []):
            case = self.repo.get(original["owner"], "case", ident)
            if case["subject_id"] != original["subject"]:
                raise EvidenceError("重新生成的事项范围不符")
        return dict(request, message=source["content"], source_message_id=source["id"])

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
            request = self._request(original)
            usage = dict(row["usage"], agent_runtime=dict(meta, regenerations=1))
            connection.execute(
                sql.SQL("UPDATE {} SET status='stale',request=%s,usage=%s WHERE owner=%s AND id=%s").format(
                    self.repo.table("core_runs")
                ),
                (Jsonb(request), Jsonb(usage), owner, ident),
            )
            self.repo.prepare_retry(owner, ident)
            return self.repo.claim_run(owner, ident, lease_seconds=150)

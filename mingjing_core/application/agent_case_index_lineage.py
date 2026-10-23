"""A completed case index grants title/status citations, never selected-case writes."""

from __future__ import annotations

from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock


def case_index_lineage(service: Any, run: dict[str, Any], result: ToolResult) -> list[dict[str, Any]]:
    if not result.ok:
        return []
    repo, owner = service.repo, run["owner"]
    with repo.transaction(owner) as connection:
        current = repo._leased(connection, owner, run["id"], run["lease_token"])
        if (
            current["runtime"] != "v4"
            or current["retry_epoch"] != run["retry_epoch"]
            or current["subject"] != run["subject"]
            or current["cancel_requested_at"] is not None
            or current["deadline_at"] is not None
            and current["deadline_at"] <= get_clock().now()
        ):
            raise LeaseConflict("事项索引不属于当前有效运行")
        thread = current["thread_id"] or current["request"].get("thread_id") or "life:" + current["subject"]
        if thread != "life:" + current["subject"] or current["request"].get("incognito") is True:
            raise ScopeError("无痕线程不能注册长期事项索引")
        step = connection.execute(
            sql.SQL(
                "SELECT seq FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='tool' "
                "AND name='case_list' AND status='completed' AND error_code IS NULL "
                "AND finished_at IS NOT NULL AND output=%s ORDER BY seq DESC LIMIT 1"
            ).format(repo.table("core_run_steps")),
            (owner, run["id"], run["retry_epoch"], Jsonb(result.model_dump())),
        ).fetchone()
        if step is None:
            raise EvidenceError("事项索引缺少本轮已完成工具步骤证明")
        rows = repo.list(owner, "case", subject=current["subject"], limit=100)
        expected = {
            "cases": [
                {"id": row["id"], "title": row["title"], "status": row["status"], "revision": row["revision"]}
                for row in rows
            ],
            "limit": 100,
        }
        if fingerprint(result.data) != fingerprint(expected):
            raise EvidenceError("事项索引与当前人物的真实只读投影不符")
        return [
            dict(
                kind="case",
                id=row["id"],
                revision=row["revision"],
                basis="case_index",
                index_only=True,
                run_id=current["id"],
                epoch=current["retry_epoch"],
                model_tool_seq=step["seq"],
                index_projection_sha256=fingerprint(expected),
            )
            for row in rows
        ]

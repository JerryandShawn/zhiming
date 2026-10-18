"""Lease-fenced application boundary for v4 tools; tools themselves never use SQL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from psycopg import sql

from mingjing_core.application.agent_tools_contracts import (
    RelativeDateParser,
    ToolContext,
    ToolResult,
    tool_input_fingerprint,
)
from mingjing_core.application.agent_tools_policy import V4FactMemory, source_policy
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.timekit.clock import Clock, get_clock

if TYPE_CHECKING:
    from psycopg import Connection

    from mingjing_core.repositories.postgres import PostgresRepository


class AgentToolsService:
    def __init__(
        self,
        repo: PostgresRepository,
        *,
        relative_parser: RelativeDateParser | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.repo, self.relative_parser, self.clock = (
            repo,
            relative_parser,
            clock or get_clock(),
        )
        self.memory = V4FactMemory(repo)

    def authority(self, connection: Connection[Any], ctx: ToolContext) -> dict[str, Any]:
        row = self.repo._leased(connection, ctx.owner, ctx.run_id, ctx.lease_token)
        if row["retry_epoch"] != ctx.epoch or row["cancel_requested_at"] is not None:
            raise LeaseConflict("工具执行批次已失效或已停止")
        if row["deadline_at"] is not None and row["deadline_at"] <= self.clock.now():
            raise LeaseConflict("工具执行时间已结束")
        if row["runtime"] != "v4" or row["subject"] != ctx.subject:
            raise ScopeError("工具人物或运行版本不符")
        self.repo.assert_scope(ctx.owner, ctx.subject)
        thread = row["thread_id"] or row["request"].get("thread_id") or "life:" + row["subject"]
        if ctx.thread_id != thread:
            raise ScopeError("工具不属于当前线程")
        self._case_scope(row, ctx)
        if any(row["state_version"].get(key) != version for key, version in ctx.source_versions.items()):
            raise ScopeError("工具不能扩展或更改本轮来源版本")
        if ctx.source_versions and not self.repo.verify_versions(ctx.owner, ctx.source_versions):
            raise EvidenceError("工具来源版本已经改变")
        step = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s FOR UPDATE").format(
                self.repo.table("core_run_steps")
            ),
            (ctx.owner, ctx.run_id, ctx.epoch, ctx.seq),
        ).fetchone()
        if step is None or (step["kind"], step["name"], step["input_fp"]) != (
            "tool",
            ctx.name,
            ctx.input_fp,
        ):
            raise EvidenceError("工具身份与持久步骤不符")
        if step["status"] not in {"started", "completed"} or step["error_code"]:
            raise EvidenceError("工具步骤已撤销")
        return row

    def _case_scope(self, row: dict[str, Any], ctx: ToolContext) -> None:
        selected = row["request"].get("case_ids", [])
        if not isinstance(selected, list) or any(not isinstance(ident, str) for ident in selected):
            raise ScopeError("持久事项范围无效")
        if set(ctx.case_ids) != set(selected) or len(ctx.case_ids) != len(set(ctx.case_ids)):
            raise ScopeError("工具不能扩展或替换本轮已选择事项")
        for ident in selected:
            if self.repo.get(ctx.owner, "case", ident)["subject_id"] != ctx.subject:
                raise ScopeError("事项不属于当前人物")

    def source(self, ctx: ToolContext, message_id: str) -> dict[str, Any]:
        run = self.repo.fetch_run(ctx.owner, ctx.run_id)
        actual = run["request"].get("source_message_id")
        if message_id != actual or ctx.source_ids and message_id not in ctx.source_ids:
            raise ScopeError("来源不在本轮受信范围")
        source = self.memory.get_source(ctx.owner, message_id)
        source_policy(source, ctx.subject, ctx.thread_id)
        if self.repo.is_revoked(ctx.owner, "message", message_id):
            raise EvidenceError("原始来源已撤销")
        return source

    def check_span(self, ctx: ToolContext, message_id: str, start: int, end: int) -> None:
        for row in self.repo.revocations(ctx.owner):
            span = row["metadata"]
            if (
                row["kind"] == "source_span"
                and span.get("message_id") == message_id
                and max(start, span["start"]) < min(end, span["end"])
            ):
                raise EvidenceError("原话区间已经撤销")

    def timezone(self, ctx: ToolContext) -> str:
        settings = self.repo.assert_scope(ctx.owner, ctx.subject)["settings"]
        return settings.get("timezone", "Asia/Shanghai")

    def execute(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        from mingjing_core.application.agent_tools_memory import execute_write
        from mingjing_core.application.agent_tools_reads import execute_read

        if ctx.name != name:
            raise EvidenceError("调用名称与受信步骤不符")
        if tool_input_fingerprint(name, arguments, ctx.source_versions) != ctx.input_fp:
            raise EvidenceError("工具实际参数与持久输入不符")
        if ctx.crisis and name not in {"time_context", "memory_search"}:
            raise ScopeError("危机模式下此工具不可用")
        writes = {"memory_write", "memory_forget", "note_write"}
        if ctx.private and name in writes:
            return ToolResult(
                ok=False,
                receipt={"write_status": "stopped", "code": "incognito"},
                summary="无痕模式未写入长期资料",
            )
        with self.repo.transaction(ctx.owner) as connection:
            self.authority(connection, ctx)
            if name in writes:
                return execute_write(self, name, arguments, ctx)
            return execute_read(self, name, arguments, ctx)

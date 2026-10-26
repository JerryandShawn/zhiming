"""Read reviewed local chapters only after an attested current-run calculation."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.agent.tools.computation_parameters import ChartSkill
from mingjing_core.application.agent_chart_lineage import chart_cache
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.skills.loader import chart_skill


def execute_chart_skill(service: Any, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
    args = ChartSkill.model_validate(arguments).model_dump()
    if ctx.name != "chart_skill" or ctx.input_fp != tool_input_fingerprint(ctx.name, args, ctx.source_versions):
        raise EvidenceError("技能调用与持久步骤不符")
    if ctx.crisis:
        raise ScopeError("当前模式下不读取命理技能")
    with service.repo.transaction(ctx.owner) as connection:
        run = service.authority(connection, ctx)
        service.source(ctx, run["request"]["source_message_id"])
        row = connection.execute(
            sql.SQL(
                "SELECT output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq<%s "
                "AND kind='tool' AND name='chart_compute' AND status='completed' AND error_code IS NULL "
                "AND finished_at IS NOT NULL ORDER BY seq DESC LIMIT 1"
            ).format(service.repo.table("core_run_steps")),
            (ctx.owner, ctx.run_id, ctx.epoch, ctx.seq),
        ).fetchone()
        if row is None:
            raise EvidenceError("本轮尚无已完成盘面，未读取技能")
        result = ToolResult.model_validate(row["output"])
        if not result.ok:
            raise EvidenceError("本轮计算未成功，未读取技能")
        # An ok flag alone cannot authorize interpretation after source change
        # or artifact withdrawal. Reuse the native cache/version attestation.
        chart_cache(service, run, result)
        data = chart_skill(args["system"], args["topic"])
        return ToolResult(ok=True, data=data, summary="已读取本地解释技能；不产生新的盘面依据")

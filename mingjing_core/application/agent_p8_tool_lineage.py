"""Only completed native date-tool output can register P8 document/Pointer aliases."""

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_p8_tools import MODELS
from mingjing_core.application.agent_tools_charts import cached_chart
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.application.p8_reference_records import verify_reference_bundle
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import fingerprint


def p8_tool_lineage(service, run, name, result):
    if not result.ok:
        return [], {}
    if name not in MODELS:
        raise EvidenceError("未注册的命理日期工具")
    with service.repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT seq,input_fp FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='tool' "
                "AND name=%s AND status='completed' AND error_code IS NULL AND finished_at IS NOT NULL "
                "AND output=%s LIMIT 2"
            ).format(service.repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"], name, Jsonb(result.model_dump())),
        ).fetchall()
    if len(rows) != 1:
        raise EvidenceError("命理日期结果缺少唯一已完成步骤")
    step = rows[0]
    ctx = ToolContext(
        run["owner"],
        run["id"],
        run["subject"],
        run["retry_epoch"],
        step["seq"],
        run["lease_token"],
        name,
        step["input_fp"],
        "life:" + run["subject"],
        source_ids=(run["request"]["source_message_id"],),
        case_ids=tuple(run["request"].get("case_ids", [])),
    )
    replay = cached_chart(service, ctx)
    if replay is None or fingerprint(replay.model_dump()) != fingerprint(result.model_dump()):
        raise EvidenceError("命理日期结果与原生缓存不符")
    ident = "agent_chart_cache_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    cache = service.repo.get(ctx.owner, "runtime_step", ident)
    return verify_reference_bundle(service, ctx, cache["snapshot"], result.data["documents"], result.data["persisted"])

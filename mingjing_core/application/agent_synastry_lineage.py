"""Only the exact completed native step can attest the temporary comparison."""

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_synastry import cache_id, cached
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import fingerprint


def synastry_lineage(service, run, result):
    if not result.ok:
        return [], {}
    with service.repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT seq,input_fp FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='tool' "
                "AND name='synastry' AND status='completed' AND error_code IS NULL AND finished_at IS NOT NULL "
                "AND output=%s LIMIT 2"
            ).format(service.repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"], Jsonb(result.model_dump())),
        ).fetchall()
        if len(rows) != 1:
            raise EvidenceError("合盘结果缺少唯一已完成步骤")
        step = rows[0]
        ctx = ToolContext(
            run["owner"],
            run["id"],
            run["subject"],
            run["retry_epoch"],
            step["seq"],
            run["lease_token"],
            "synastry",
            step["input_fp"],
            run.get("thread_id") or "life:" + run["subject"],
            source_ids=(run["request"]["source_message_id"],),
            case_ids=tuple(run["request"].get("case_ids", [])),
        )
        service.authority(connection, ctx)
        replay = cached(service, ctx)
        if replay is None or fingerprint(replay.model_dump()) != fingerprint(result.model_dump()):
            raise EvidenceError("合盘结果与原生临时缓存不符")
        row = service.repo.get(ctx.owner, "runtime_step", cache_id(ctx))
        return [], dict(row["source_versions"], **{"entity:runtime_step:" + row["id"]: row["revision"]})

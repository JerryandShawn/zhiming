"""Native P8 date tools: short authority transactions around isolated calculation."""

from typing import Any

from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.adapters.charts.p8_worker import source_hashes
from mingjing_core.agent.tools.p8_parameters import Almanac, DailyTransit, WindowSearch
from mingjing_core.application.agent_p8_charts import remaining_reference_slots
from mingjing_core.application.agent_tool_persistence import privacy_refusal
from mingjing_core.application.agent_tools_charts import cached_chart, prepare_chart, recheck_chart, save_chart_cache
from mingjing_core.application.agent_tools_contracts import ToolResult, tool_input_fingerprint
from mingjing_core.application.charts_documents import verify_p8_document
from mingjing_core.application.charts_natal import natal_request
from mingjing_core.application.p8_chart_service import P8CalculationUnavailable
from mingjing_core.application.p8_reference_records import persist_reference_bundle, selected_references
from mingjing_core.domain.contracts import CoreError, EvidenceError, ScopeError
from mingjing_core.knowledge.registry import resolve_pointer
from mingjing_core.repositories.postgres import fingerprint
from subprocess import TimeoutExpired

MODELS = {"daily_transit": DailyTransit, "window_search": WindowSearch, "almanac": Almanac}


def public_snapshot(service: Any, ctx: Any) -> dict:
    with service.repo.transaction(ctx.owner) as connection:
        run = service.authority(connection, ctx)
        source = service.source(ctx, run["request"]["source_message_id"])
        return {
            "owner_user_id": ctx.owner,
            "subject_id": ctx.subject,
            "revision": service.repo.get_revision(ctx.owner),
            "versions": {"message:" + source["id"]: source["revision"]},
            "source_ids": [source["id"]],
            "profile": {},
            "facts": [],
        }


def calculate(name: str, args: dict, ctx: Any, snapshot: dict) -> dict:
    sources = source_hashes()
    natal = (
        None
        if name == "almanac"
        else natal_request(
            snapshot,
            owner=ctx.owner,
            subject=ctx.subject,
            operation_id=ctx.operation_id,
            as_of=args.get("date", args.get("start_date")),
        )
    )
    try:
        adapter = P8ChartAdapter(ctx.owner)
        if name == "almanac":
            payload = adapter.almanac(args["date"])
        elif name == "daily_transit":
            payload = adapter.daily_transit(natal, args["date"])
        else:
            payload = adapter.window_search(
                natal,
                {key: args[key] for key in ("start_date", "end_date")},
                args["purpose"],
                offset=args["offset"],
                limit=args["limit"],
            )
    except CoreError:
        raise
    except (OSError, RuntimeError, ValueError, TypeError, TimeoutExpired):
        raise P8CalculationUnavailable("本次日期计算未完成，未采用未经核对的结果") from None
    return verify_p8_document(
        payload,
        kind=name,
        owner=ctx.owner,
        subject=ctx.subject,
        revision=snapshot["revision"],
        operation_id=ctx.operation_id,
        source_sha256=sources,
    )


def execute_date_tool(service: Any, name: str, arguments: dict, ctx: Any) -> ToolResult:
    args = MODELS[name].model_validate(arguments).model_dump()
    if ctx.name != name or ctx.input_fp != tool_input_fingerprint(name, args, ctx.source_versions):
        raise EvidenceError("日期计算与原生步骤参数不符")
    if ctx.private or ctx.crisis:
        raise ScopeError("当前模式不进行命理日期计算")
    if getattr(service.repo._local, "connection", None) is not None:
        raise EvidenceError("日期计算必须在外层数据库事务外执行")
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if stopped := privacy_refusal(service, name, args, ctx):
            return stopped
    if cached := cached_chart(service, ctx):
        return cached
    snapshot = public_snapshot(service, ctx) if name == "almanac" else prepare_chart(service, ctx)
    doc = calculate(name, args, ctx, snapshot)
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if stopped := privacy_refusal(service, name, args, ctx):
            return stopped
        recheck_chart(service, ctx, snapshot)
        limit = remaining_reference_slots(service, ctx, connection)
        persisted = persist_reference_bundle(service, ctx, snapshot, [doc], limit=limit)
        views = [
            dict(row, native_id="p8-ref-" + fingerprint(row), value=resolve_pointer(doc["payload"], row["pointer"]))
            for row in selected_references([doc], limit=limit)
        ]
        result = ToolResult(
            ok=True,
            data={
                "adapter_mode": "p8_v1_1",
                "tool_name": name,
                "arguments": args,
                "calculation": doc["payload"],
                "documents": [doc],
                "persisted": persisted,
                "requested_system": None,
                "reference_views": views,
                "alias_registration": "requires_trusted_run_registry",
            },
            summary="日期计算已返回原生依据；不代表现实结果保证，不写入用户事实",
        )
        save_chart_cache(service, ctx, snapshot, result)
        return result

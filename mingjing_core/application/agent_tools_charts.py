"""Two short PG transactions around pure calculation; no long-held writer lock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.agent.tools.computation_parameters import ChartCompute
from mingjing_core.application.agent_tool_persistence import privacy_refusal
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.application.agent_tools_projection import sources_active
from mingjing_core.application.charts_projection import chart_diagnostics, public_errors
from mingjing_core.application.charts_service import ChartsService, verify_calculation_scope
from mingjing_core.domain.contracts import CoreError, EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import fingerprint

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService

UNSUPPORTED = ("true_solar_time_basis", "boundary_alerts", "western_timing", "transit_interval_search")


class ChartInputsRequired(EvidenceError):
    code = "MISSING_INPUT"


class ChartCalculationUnavailable(EvidenceError):
    code = "CALCULATION_ERROR"


def prepare_chart(service: AgentToolsService, ctx: ToolContext) -> dict[str, Any]:
    with service.repo.transaction(ctx.owner) as connection:
        run = service.authority(connection, ctx)
        source = service.source(ctx, run["request"]["source_message_id"])
        facts = [
            row
            for row in service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
            if (row.get("field") == "gender" or str(row.get("field", "")).startswith("birth."))
            and sources_active(service, row, ctx)
        ]
        snapshot = {
            "owner_user_id": ctx.owner,
            "subject_id": ctx.subject,
            "revision": service.repo.get_revision(ctx.owner),
            "source_ids": [source["id"]],
            "versions": service.repo.versions(ctx.owner, ctx.subject, list(ctx.case_ids)),
        }
        snapshot["versions"]["message:" + source["id"]] = source["revision"]
        profile, conflicts = {}, set()
        for fact in facts:
            key = fact["field"]
            if key in profile and profile[key] != fact.get("value"):
                conflicts.add(key)
            profile[key] = fact.get("value")
            snapshot["versions"]["fact:" + fact["id"]] = fact["revision"]
            for ref in fact.get("source_refs", []):
                snapshot["versions"]["message:" + ref["message_id"]] = ref["version"]
        for key in conflicts:
            profile.pop(key, None)
        if not profile.get("birth.solar_datetime"):
            raise ChartInputsRequired("请先通过资料确认流程核对出生资料")
        snapshot.update(profile=profile, profile_conflicts=sorted(conflicts), facts=facts)
        return snapshot


def recheck_chart(service: AgentToolsService, ctx: ToolContext, snapshot: dict[str, Any]) -> None:
    if not service.repo.verify_versions(ctx.owner, snapshot["versions"]):
        raise RevisionConflict("计算期间授权资料已改变，结果未采用")
    for fact in snapshot["facts"]:
        current = service.repo.get(ctx.owner, "fact", fact["id"], include_deleted=True)
        if current["revision"] != fact["revision"] or not sources_active(service, current, ctx):
            raise EvidenceError("计算来源已撤销或改变，结果未采用")


def persist_calculation(
    service: AgentToolsService, ctx: ToolContext, snapshot: dict[str, Any], evaluation: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    records: dict[str, list[dict[str, Any]]] = {"artifacts": [], "claims": []}
    common = {
        "run_id": ctx.run_id,
        "epoch": ctx.epoch,
        "source_versions": snapshot["versions"],
        "source_ids": snapshot["source_ids"],
        "used_fact_ids": [row["id"] for row in snapshot["facts"]],
        "source_refs": [ref for row in snapshot["facts"] for ref in row.get("source_refs", [])],
    }
    for kind, key, native in (
        ("artifact", "artifacts", evaluation["calculation"]["artifacts"]),
        ("interpretive_claim", "claims", {row["claim_id"]: row for row in evaluation["claims"]}),
    ):
        for native_id, value in native.items():
            ident = "agent_" + kind + "_" + fingerprint([ctx.owner, ctx.operation_id, native_id])[:32]
            content = dict(common, **{"artifact" if kind == "artifact" else "claim": value})
            if kind == "artifact":
                content["features"] = {
                    name: item
                    for name, item in evaluation["calculation"]["features"].items()
                    if item["artifact_id"] == native_id
                }
                content["profile"] = evaluation["calculation"]["profiles"][value["profile_id"]]
            row = service.repo.put(
                ctx.owner,
                kind,
                ident,
                content,
                subject=ctx.subject,
                expected_revision=0,
                operation_id=ctx.operation_id + ":" + kind + ":" + native_id,
            )
            records[key].append({"id": row["id"], "native_id": native_id, "revision": row["revision"]})
    return records


def cached_chart(service: AgentToolsService, ctx: ToolContext) -> ToolResult | None:
    ident = "agent_chart_cache_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    with service.repo.transaction(ctx.owner) as connection:
        run = service.authority(connection, ctx)
        service.source(ctx, run["request"]["source_message_id"])
        try:
            cached = service.repo.get(ctx.owner, "runtime_step", ident, include_deleted=True)
        except ScopeError:
            return None
        if cached["status"] != "active" or cached.get("input_fp") != ctx.input_fp:
            raise EvidenceError("原计算步骤已撤销或改变，不能重新生成旧结果")
        recheck_chart(service, ctx, cached["snapshot"])
        result = ToolResult.model_validate(cached["tool_output"])
        if result.data.get("adapter_mode") == "p8_v1_1":
            from mingjing_core.application.p8_reference_records import verify_reference_bundle

            verify_reference_bundle(
                service,
                ctx,
                cached["snapshot"],
                result.data["documents"],
                result.data["persisted"],
                system=result.data["requested_system"],
            )
            return result
        for key, kind in (("artifacts", "artifact"), ("claims", "interpretive_claim")):
            for record in result.data["persisted"][key]:
                row = service.repo.get(ctx.owner, kind, record["id"], include_deleted=True)
                if (
                    row["status"] != "active"
                    or row["revision"] != record["revision"]
                    or row.get("run_id") != ctx.run_id
                    or row.get("epoch") != ctx.epoch
                ):
                    raise EvidenceError("已存盘面或解释依据已失效")
        return result


def chart_result(evaluation: dict[str, Any], records: dict[str, Any]) -> ToolResult:
    diagnostics = chart_diagnostics(evaluation["calculation"], evaluation["gaps"])
    public = dict(
        evaluation,
        calculation=dict(evaluation["calculation"], errors=public_errors(evaluation["calculation"]["errors"])),
    )
    return ToolResult(
        ok=bool(evaluation["calculation"]["artifacts"]),
        data=dict(
            public,
            persisted=records,
            adapter_mode="legacy_v3",
            diagnostics=diagnostics,
            unsupported_capabilities=list(UNSUPPORTED),
            alias_registration="requires_trusted_run_registry",
        ),
        summary="盘面计算已返回真实产物" if evaluation["calculation"]["artifacts"] else "盘面计算未取得可用产物",
    )


def save_chart_cache(
    service: AgentToolsService, ctx: ToolContext, snapshot: dict[str, Any], result: ToolResult
) -> None:
    ident = "agent_chart_cache_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    service.repo.put(
        ctx.owner,
        "runtime_step",
        ident,
        {
            "run_id": ctx.run_id,
            "epoch": ctx.epoch,
            "input_fp": ctx.input_fp,
            "snapshot": snapshot,
            "tool_output": result.model_dump(),
            "source_ids": snapshot["source_ids"],
            "source_refs": [ref for row in snapshot["facts"] for ref in row.get("source_refs", [])],
            "used_fact_ids": [row["id"] for row in snapshot["facts"]],
        },
        subject=ctx.subject,
        expected_revision=0,
        operation_id=ctx.operation_id + ":chart_cache",
    )


def execute_chart(
    service: AgentToolsService, arguments: dict[str, Any], ctx: ToolContext, *, charts: ChartsService | None = None
) -> ToolResult:
    args = ChartCompute.model_validate(arguments).model_dump()
    if ctx.name != "chart_compute" or tool_input_fingerprint(ctx.name, args, ctx.source_versions) != ctx.input_fp:
        raise EvidenceError("计算工具参数与持久步骤不符")
    if ctx.private:
        raise ScopeError("当前无痕计算尚不支持临时出生资料，未读取或保存档案")
    if ctx.crisis:
        raise ScopeError("危机模式下不进行排盘")
    if getattr(service.repo._local, "connection", None) is not None:
        raise EvidenceError("排盘必须在外层数据库事务之外执行")
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if stopped := privacy_refusal(service, "chart_compute", args, ctx):
            return stopped
    cached = cached_chart(service, ctx)
    if cached is not None:
        return cached
    snapshot = prepare_chart(service, ctx)
    engine = charts or ChartsService()
    from mingjing_core.application.agent_p8_charts import execute_p8, uses_p8

    if uses_p8(snapshot, args["system"]):
        return execute_p8(service, ctx, args, snapshot, engine)
    try:
        evaluation = engine.evaluate(
            ctx.owner, ctx.subject, snapshot, args["target"], [args["system"]], topic="general", scale=args["scale"]
        )
    except CoreError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise ChartCalculationUnavailable("本次排盘未完成，未返回未经验证的盘面") from None
    verify_calculation_scope(
        evaluation["calculation"],
        ctx.owner,
        ctx.subject,
        snapshot["revision"],
        target=args["target"],
        system=args["system"],
    )
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if stopped := privacy_refusal(service, "chart_compute", args, ctx):
            return stopped
        recheck_chart(service, ctx, snapshot)
        records = persist_calculation(service, ctx, snapshot, evaluation)
        result = chart_result(evaluation, records)
        if args["system"] in {"bazi", "ziwei"}:
            result.data["basis_notice"] = "旧口径，未做真太阳时与交界提示；区间或未知时刻只作分支采样"
        save_chart_cache(service, ctx, snapshot, result)
        return result

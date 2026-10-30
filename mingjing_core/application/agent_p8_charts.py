"""P8 chart execution/cache attestation under native Agent step authority."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.application.agent_tool_persistence import privacy_refusal
from mingjing_core.application.agent_tools_charts import recheck_chart, save_chart_cache
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.p8_reference_records import persist_reference_bundle, selected_references
from mingjing_core.knowledge.registry import resolve_pointer
from mingjing_core.repositories.postgres import fingerprint


def uses_p8(snapshot: dict, system: str) -> bool:
    profile = snapshot["profile"]
    return system in {"bazi", "ziwei"} and not (
        profile.get("birth.time_unknown") is True
        or profile.get("birth.precision") in {"approximate", "interval", "unknown"}
    )


def execute_p8(service: Any, ctx: Any, args: dict, snapshot: dict, engine: Any) -> ToolResult:
    evaluation = engine.evaluate_time_basis(
        ctx.owner, ctx.subject, snapshot, args["target"], operation_id=ctx.operation_id
    )
    documents = evaluation["documents"]
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if stopped := privacy_refusal(service, "chart_compute", args, ctx):
            return stopped
        recheck_chart(service, ctx, snapshot)
        limit = remaining_reference_slots(service, ctx, connection)
        persisted = persist_reference_bundle(service, ctx, snapshot, documents, system=args["system"], limit=limit)
        views = []
        by_id = {doc["document_id"]: doc for doc in documents}
        for reference in selected_references(documents, args["system"], limit):
            views.append(
                dict(
                    reference,
                    native_id="p8-ref-" + fingerprint(reference),
                    value=resolve_pointer(by_id[reference["document_id"]]["payload"], reference["pointer"]),
                )
            )
        result = ToolResult(
            ok=True,
            data=dict(
                evaluation,
                persisted=persisted,
                requested_system=args["system"],
                target=args["target"],
                scale=args["scale"],
                reference_views=views,
                alias_registration="requires_trusted_run_registry",
            ),
            summary="已按真太阳时口径计算；保留北京时间差异与临界候选，不改出生资料",
        )
        save_chart_cache(service, ctx, snapshot, result)
        return result


def remaining_reference_slots(service: Any, ctx: Any, connection: Any) -> int:
    """Count actual completed native outputs, never a model-provided allowance."""
    rows = connection.execute(
        sql.SQL(
            "SELECT output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq<%s "
            "AND kind='tool' AND status='completed' AND error_code IS NULL AND finished_at IS NOT NULL "
            "AND name IN ('chart_compute','daily_transit','window_search','almanac','synastry')"
        ).format(service.repo.table("core_run_steps")),
        (ctx.owner, ctx.run_id, ctx.epoch, ctx.seq),
    ).fetchall()
    used = set()
    for row in rows:
        output = row["output"] or {}
        if output.get("ok") is not True:
            continue
        persisted = output.get("data", {}).get("persisted", {})
        for group in ("artifacts", "claims"):
            used.update((group, item["id"]) for item in persisted.get(group, []))
    return max(0, 10 - len(used))


WINDOW_HITS_PER_SIDE = 3
WINDOW_WEIGHT_KEYS = ("version", "school", "source", "layer_factors", "limits", "prediction_validated")


def window_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """R54: bound window_search for the model; native order and scores are kept, nothing re-scored.

    Per day only the three largest positive and the three most negative hits stay visible
    (deterministic: contribution, then native rule_hit_index). Omitted counts are explicit so the
    model cannot present a trimmed list as complete; the full document stays private.
    """
    days, omitted_any = [], False
    for row in payload["candidates"]:
        positive = sorted(row["positive_hits"], key=lambda hit: (-hit["contribution"], hit["rule_hit_index"]))
        negative = sorted(row["negative_hits"], key=lambda hit: (hit["contribution"], hit["rule_hit_index"]))
        omitted = {
            "positive_hits": max(0, len(positive) - WINDOW_HITS_PER_SIDE),
            "negative_hits": max(0, len(negative) - WINDOW_HITS_PER_SIDE),
            "neutral_hits": len(row.get("neutral_hits", [])),
        }
        omitted_any = omitted_any or any(omitted.values())
        days.append(
            {key: row[key] for key in ("date", "rank", "score")}
            | {
                "positive_hits": positive[:WINDOW_HITS_PER_SIDE],
                "negative_hits": negative[:WINDOW_HITS_PER_SIDE],
                "omitted": omitted,
            }
        )
    return {
        key: payload[key] for key in ("range", "purpose", "method", "trace", "pagination") if key in payload
    } | {
        "weights": {key: payload["weights"][key] for key in WINDOW_WEIGHT_KEYS if key in payload.get("weights", {})},
        "candidates": days,
        "projection_truncated": omitted_any or bool(payload.get("observations")),
        "omitted_observations": len(payload.get("observations", [])),
    }


def tool_projection(data: dict[str, Any]) -> dict[str, Any]:
    """Full native documents stay private; actual selected references reach the model."""
    native = data["calculation"]
    if data.get("tool_name"):
        return {key: data[key] for key in ("adapter_mode", "tool_name", "arguments", "reference_views")} | {
            "tool_data": window_projection(native["data"]) if data["tool_name"] == "window_search" else native["data"],
            "limits": native.get("limits", []),
        }
    summaries = []
    for chart in native["charts"]:
        if chart.get("visible_by_default") is not True:
            continue
        basis, column = chart["time_basis"], chart["ziwei_column"]
        summaries.append(
            {
                "chart_id": chart["id"],
                "basis": basis["basis"],
                "role": chart["interpretation_role"],
                "pillars": chart["data"]["pillars"],
                "pillar_method": basis["pillar_method"],
                "ziwei": {key: column[key] for key in ("ming_gong", "shen_gong", "method")},
            }
        )
    return {
        key: data[key]
        for key in (
            "adapter_mode",
            "requested_system",
            "target",
            "scale",
            "reference_views",
            "boundary_alerts",
            "physical_instant_confirmation_required",
            "unsupported_capabilities",
        )
    } | {
        "chart_summaries": summaries,
        "interpretation": native["interpretation"],
        "record_policy": native["record_policy"],
    }

"""Attest chart aliases from completed current-epoch steps and real PG payloads."""

from __future__ import annotations

from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_tools_charts import cached_chart
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.application.charts_service import verify_calculation_scope
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.domain.json_values import ensure_finite_json
from mingjing_core.knowledge import KnowledgeRegistry
from mingjing_core.repositories.postgres import fingerprint


def completed_chart_context(service: Any, run: dict[str, Any], result: ToolResult) -> ToolContext:
    ensure_finite_json(result.model_dump())
    with service.repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT seq,input_fp FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='tool' "
                "AND name='chart_compute' AND status='completed' AND error_code IS NULL "
                "AND finished_at IS NOT NULL AND output=%s LIMIT 2"
            ).format(service.repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"], Jsonb(result.model_dump())),
        ).fetchall()
    if len(rows) != 1:
        raise EvidenceError("盘面结果缺少本批次唯一已完成工具步骤")
    step = rows[0]
    return ToolContext(
        run["owner"],
        run["id"],
        run["subject"],
        run["retry_epoch"],
        step["seq"],
        run["lease_token"],
        "chart_compute",
        step["input_fp"],
        "life:" + run["subject"],
        source_ids=(run["request"]["source_message_id"],),
        case_ids=tuple(run["request"].get("case_ids", [])),
    )


def chart_cache(service: Any, run: dict[str, Any], result: ToolResult) -> tuple[dict[str, Any], dict[str, Any]]:
    ctx = completed_chart_context(service, run, result)
    replay = cached_chart(service, ctx)
    if replay is None or fingerprint(replay.model_dump()) != fingerprint(result.model_dump()):
        raise EvidenceError("盘面结果与受保护计算步骤不符")
    ident = "agent_chart_cache_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    cached = service.repo.get(ctx.owner, "runtime_step", ident)
    if cached.get("run_id") != run["id"] or cached.get("epoch") != run["retry_epoch"]:
        raise ScopeError("计算缓存不属于当前运行批次")
    snapshot, calculation = cached["snapshot"], result.data["calculation"]
    if result.data.get("adapter_mode") == "p8_v1_1":
        return cached, calculation
    verify_calculation_scope(calculation, ctx.owner, ctx.subject, snapshot["revision"])
    if not KnowledgeRegistry.load_builtin().revalidate_claims(calculation, result.data["claims"])["eligible"]:
        raise EvidenceError("解释依据无法从本次真实盘面复核")
    if not service.repo.verify_versions(ctx.owner, snapshot["versions"]):
        raise RevisionConflict("盘面所依据的资料版本已改变")
    return cached, calculation


def native_payload(
    calculation: dict[str, Any], claims: dict[str, Any], kind: str, native_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    if kind == "interpretive_claim":
        if native_id not in claims:
            raise EvidenceError("解释依据不在真实计算步骤中")
        return claims[native_id], {}
    artifact = calculation["artifacts"].get(native_id)
    if artifact is None:
        raise EvidenceError("盘面产物不在真实计算步骤中")
    extra = {
        "features": {key: row for key, row in calculation["features"].items() if row["artifact_id"] == native_id},
        "profile": calculation["profiles"][artifact["profile_id"]],
    }
    return artifact, extra


def attest_record(
    service: Any,
    run: dict[str, Any],
    cached: dict[str, Any],
    calculation: dict[str, Any],
    claims: dict[str, Any],
    kind: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != {"id", "native_id", "revision"}:
        raise EvidenceError("盘面持久记录投影无效")
    row = service.repo.get(run["owner"], kind, record["id"], include_deleted=True)
    if (
        row["status"] != "active"
        or row["subject_id"] != run["subject"]
        or row.get("run_id") != run["id"]
        or type(row.get("epoch")) is not int
        or row["epoch"] != run["retry_epoch"]
    ):
        raise ScopeError("盘面记录不属于当前有效运行")
    if type(record["revision"]) is not int or row["revision"] != record["revision"]:
        raise RevisionConflict("盘面记录已被改动")
    value, extra = native_payload(calculation, claims, kind, record["native_id"])
    expected = {
        "artifact" if kind == "artifact" else "claim": value,
        **extra,
        "source_versions": cached["snapshot"]["versions"],
        "source_ids": cached["snapshot"]["source_ids"],
        "used_fact_ids": [item["id"] for item in cached["snapshot"]["facts"]],
        "source_refs": [ref for item in cached["snapshot"]["facts"] for ref in item.get("source_refs", [])],
    }
    if any(fingerprint(row.get(key)) != fingerprint(item) for key, item in expected.items()):
        raise EvidenceError("盘面或解释记录的内容绑定不符")
    return {
        "kind": kind,
        "id": row["id"],
        "revision": row["revision"],
        "native_id": record["native_id"],
        "run_id": run["id"],
        "epoch": run["retry_epoch"],
        "calculation_revision": cached["snapshot"]["revision"],
        "basis": "legacy_validated_artifact" if kind == "artifact" else "legacy_validated_rule",
        "source_sha256": fingerprint(expected),
    }


def chart_lineage(service: Any, run: dict[str, Any], result: ToolResult) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Only successful server results can add c/r; failed tools add no aliases."""
    if not result.ok:
        return [], {}
    cached, calculation = chart_cache(service, run, result)
    if result.data.get("adapter_mode") == "p8_v1_1":
        from mingjing_core.application.p8_reference_records import verify_reference_bundle

        return verify_reference_bundle(
            service,
            completed_chart_context(service, run, result),
            cached["snapshot"],
            result.data["documents"],
            result.data["persisted"],
            system=result.data["requested_system"],
        )
    claims = {row["claim_id"]: row for row in result.data["claims"]}
    records = []
    persisted = result.data.get("persisted")
    if not isinstance(persisted, dict) or set(persisted) != {"artifacts", "claims"}:
        raise EvidenceError("计算步骤缺少精确持久产物清单")
    for group, kind, native in (
        ("artifacts", "artifact", calculation["artifacts"]),
        ("claims", "interpretive_claim", claims),
    ):
        rows = persisted[group]
        if (
            not isinstance(rows, list)
            or any(not isinstance(row, dict) for row in rows)
            or {row.get("native_id") for row in rows} != set(native)
            or len(rows) != len(native)
        ):
            raise EvidenceError("计算步骤的持久产物清单不完整")
        records.extend(attest_record(service, run, cached, calculation, claims, kind, row) for row in rows)
    return records, cached["snapshot"]["versions"]

"""Validate trusted P8 worker outputs before storing or registering references.

Source digests are a binding, not authentication. Callers must obtain payloads
from their own scoped adapter invocation, never from model or HTTP arguments.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from mingjing_core.adapters.charts.tool_evidence import content_hash
from mingjing_core.application.agent_tools_charts import recheck_chart
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.domain.contracts import CoreError, EvidenceError, ScopeError
from mingjing_core.domain.json_values import ensure_finite_json
from mingjing_core.knowledge.registry import resolve_pointer
from mingjing_core.repositories.postgres import fingerprint

VERSIONS = {
    "time_basis": "p8-time-basis-readonly-v2-review23",
    "daily_transit": "p8-daily-transit-v1",
    "window_search": "p8-window-search-v1",
    "almanac": "p8-almanac-v1",
}
SCOPE_FIELDS = ("owner_user_id", "subject_id", "revision", "operation_id")


def _scope(actual: Any, expected: dict[str, Any]) -> None:
    if not isinstance(actual, dict) or any(actual.get(key) != expected[key] for key in SCOPE_FIELDS):
        raise ScopeError("P8产物归属或操作绑定不符")
    if type(actual.get("revision")) is not int:
        raise EvidenceError("P8产物修订类型无效")


def _sources(sources: Any) -> None:
    if not isinstance(sources, dict) or not sources:
        raise EvidenceError("P8产物缺少受信计算来源")
    if any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for key, value in sources.items()
    ):
        raise EvidenceError("P8产物计算来源摘要无效")


def lifted_pointer(pointer: str, chart_index: int) -> str:
    """Only chart-local /data paths are rebased; already absolute paths stay so."""
    if type(chart_index) is not int or chart_index < 0 or not isinstance(pointer, str):
        raise EvidenceError("P8盘面引用坐标无效")
    return f"/charts/{chart_index}" + pointer if pointer.startswith("/data/") else pointer


def _rule_paths(root: dict[str, Any], hit: Any, *, chart_index: int | None = None) -> list[str]:
    if not isinstance(hit, dict) or hit.get("met") is not True:
        raise EvidenceError("P8解释引用必须为实际命中规则")
    if not all(isinstance(hit.get(key), str) and hit[key] for key in ("rule_id", "school")) or not (
        isinstance(hit.get("source"), (str, dict)) and hit["source"]
    ):
        raise EvidenceError("P8解释引用缺少具名规则来源")
    paths = hit.get("evidence_paths")
    if not isinstance(paths, list) or not paths or any(not isinstance(path, str) for path in paths):
        raise EvidenceError("P8规则缺少真实盘面依据")
    lifted = [lifted_pointer(path, chart_index) if chart_index is not None else path for path in paths]
    for path in lifted:
        resolve_pointer(root, path)
    return lifted


def reference_rows(payload: dict[str, Any], kind: str, document_id: str) -> list[dict[str, Any]]:
    """Return document-relative rows, never trust upstream short alias names."""
    rules: list[tuple[str, dict[str, Any], int | None]] = []
    if kind == "time_basis":
        if not isinstance(payload.get("charts"), list) or not payload["charts"]:
            raise EvidenceError("P8时间口径产物缺少真实盘面")
        for index, chart in enumerate(payload["charts"]):
            hits = chart["data"]["p8"].get("rule_hits", [])
            if not isinstance(hits, list):
                raise EvidenceError("P8盘面规则索引无效")
            rules.extend((f"/charts/{index}/data/p8/rule_hits/{n}", hit, index) for n, hit in enumerate(hits))
        alerts = payload.get("boundary_alerts", [])
        if not isinstance(alerts, list):
            raise EvidenceError("P8临界提示索引无效")
        for index, alert in enumerate(alerts):
            _boundary_binding(payload, alert)
            rules.append((f"/boundary_alerts/{index}", alert, None))
    else:
        if not isinstance(payload.get("rule_hits"), list):
            raise EvidenceError("P8工具规则索引无效")
        rules.extend((f"/rule_hits/{n}", hit, None) for n, hit in enumerate(payload["rule_hits"]))
    evidence, rows = {}, []
    for rule_path, hit, chart_index in rules:
        paths = _rule_paths(payload, hit, chart_index=chart_index)
        for path in paths:
            evidence[path] = {
                "kind": "chart",
                "document_id": document_id,
                "pointer": path,
                "value_sha256": content_hash(resolve_pointer(payload, path)),
            }
        rows.append(
            {
                "kind": "rule",
                "document_id": document_id,
                "pointer": rule_path,
                "value_sha256": content_hash(resolve_pointer(payload, rule_path)),
                "evidence_pointers": paths,
            }
        )
    if kind == "time_basis":
        from mingjing_core.application.p8_ziwei_references import ziwei_reference_rows

        for row in ziwei_reference_rows(payload, document_id):
            evidence[row["pointer"]] = row
    return list(evidence.values()) + rows


def _boundary_binding(payload: dict[str, Any], alert: Any) -> None:
    """A school choice cannot invent or resolve a physical birth instant."""
    if (
        not isinstance(alert, dict)
        or alert.get("critical") is not True
        or alert.get("met") is not True
        or alert.get("default_formula_changed") is not False
        or not isinstance(alert.get("rules_version"), str)
        or not alert["rules_version"]
        or not isinstance(alert.get("instant_id"), str)
        or not alert["instant_id"]
        or not isinstance(alert.get("alternatives"), list)
        or not alert["alternatives"]
    ):
        raise EvidenceError("P8临界提示必须保留真实命中与候选")
    charts = [
        chart
        for chart in payload["charts"]
        if chart["time_basis"]["basis"] == "true_solar" and chart["time_basis"]["instant_id"] == alert["instant_id"]
    ]
    if len(charts) != 1:
        raise EvidenceError("P8临界提示没有唯一真实主盘")
    candidate = charts[0]["time_basis"]
    if (
        alert.get("source_instant_id") != alert["instant_id"]
        or alert.get("source_utc") != candidate["utc"]
        or alert.get("current_pillars") != candidate["pillars"]
    ):
        raise EvidenceError("P8临界提示与主盘时刻或原柱不符")
    paths = alert.get("evidence_paths")
    if not isinstance(paths, list) or not paths:
        raise EvidenceError("P8临界提示缺少真实时间依据")
    for path in paths:
        if (
            not isinstance(path, str)
            or re.fullmatch(
                r"/time_basis/items/\d+/source_variants/\d+/(coordinate_datetime|pillars|solar_time|jie_uncertainty)",
                path,
            )
            is None
        ):
            raise EvidenceError("P8临界提示必须引用本次时间口径产物")
        source = resolve_pointer(payload, path.rsplit("/", 1)[0])
        if source != candidate:
            raise EvidenceError("P8临界提示不能借用其他候选的依据")
        value = resolve_pointer(payload, path)
        # Pointer existence is necessary; the native rule itself remains the
        # source of measured seconds, alternatives and affected pillars.
        ensure_finite_json(value)


def verify_p8_document(
    payload: dict[str, Any],
    *,
    kind: str,
    owner: str,
    subject: str,
    revision: int,
    operation_id: str,
    source_sha256: dict[str, str],
) -> dict[str, Any]:
    """Scope an adapter result to the exact invocation and derive its envelope."""
    try:
        ensure_finite_json(payload)
        _sources(source_sha256)
        if (
            type(revision) is not int
            or revision < 0
            or any(not isinstance(value, str) or not value for value in (owner, subject, operation_id))
        ):
            raise EvidenceError("P8受信调用身份无效")
        if kind not in VERSIONS or not isinstance(payload, dict) or payload.get("version") != VERSIONS[kind]:
            raise EvidenceError("P8产物类型或版本无效")
        scope = dict(zip(SCOPE_FIELDS, (owner, subject, revision, operation_id), strict=True))
        if kind == "time_basis":
            _scope(payload, scope)
            if payload.get("source_sha256") != source_sha256:
                raise EvidenceError("P8时间口径计算来源不符")
        else:
            if kind == "almanac":
                if payload.get("scope") is not None:
                    raise ScopeError("黄历结果不应包含私人资料归属")
            else:
                _scope(payload.get("scope"), scope)
            native_root = {key: payload[key] for key in ("version", "scope", "data", "rule_hits", "sources")}
            if payload.get("document_id") != "tool-" + content_hash(native_root):
                raise EvidenceError("P8工具内容摘要不符")
        identity = {"scope": scope, "kind": kind, "source_sha256": source_sha256, "payload": payload}
        document_id = "doc-" + content_hash(identity)
        references = reference_rows(payload, kind, document_id)
        return deepcopy(dict(identity, document_id=document_id, references=references))
    except CoreError:
        raise
    except (KeyError, TypeError, ValueError, IndexError):
        raise EvidenceError("P8产物结构或引用校验未通过") from None


def persist_documents(
    service: Any, ctx: ToolContext, snapshot: dict[str, Any], documents: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Persist verified invocations atomically under the native lease/privacy fence."""
    if ctx.private or ctx.crisis:
        raise ScopeError("当前模式下不保存命理档案")
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        recheck_chart(service, ctx, snapshot)
        checked = [
            verify_p8_document(
                doc["payload"],
                kind=doc["kind"],
                owner=ctx.owner,
                subject=ctx.subject,
                revision=snapshot["revision"],
                operation_id=ctx.operation_id,
                source_sha256=doc["source_sha256"],
            )
            for doc in documents
        ]
        if fingerprint(checked) != fingerprint(documents):
            raise EvidenceError("P8已核验产物内容已改变")
        records = []
        for doc in checked:
            row = service.repo.put(
                ctx.owner,
                "artifact",
                "agent_p8_" + fingerprint([ctx.owner, ctx.operation_id, doc["document_id"]])[:32],
                {
                    "p8_document": doc,
                    "run_id": ctx.run_id,
                    "epoch": ctx.epoch,
                    "source_versions": snapshot["versions"],
                    "source_ids": snapshot["source_ids"],
                    "used_fact_ids": [fact["id"] for fact in snapshot["facts"]],
                    "source_refs": [ref for fact in snapshot["facts"] for ref in fact.get("source_refs", [])],
                },
                subject=ctx.subject,
                expected_revision=0,
                operation_id=ctx.operation_id + ":p8:" + doc["document_id"],
            )
            if row["status"] != "active":
                raise EvidenceError("P8原产物已撤销，不得复活")
            records.append({"id": row["id"], "revision": row["revision"], "document_id": doc["document_id"]})
        return records

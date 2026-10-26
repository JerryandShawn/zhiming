"""Native document/Pointer records behind the future current-run alias gate."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.agent_tools_charts import recheck_chart
from mingjing_core.application.charts_documents import persist_documents, verify_p8_document
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import fingerprint


def selected_references(
    documents: list[dict[str, Any]], system: str | None = None, limit: int = 10
) -> list[dict[str, Any]]:
    """At most ten rows; a rule never loses its actual chart dependencies."""
    if type(limit) is not int or not 0 <= limit <= 10:
        raise EvidenceError("P8本轮引用数量限制无效")
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for doc in documents:
        refs = {
            row["pointer"]: row
            for row in doc["references"]
            if system != "ziwei" or not row["pointer"].startswith("/charts/") or "/ziwei_column" in row["pointer"]
        }
        if system == "bazi":
            refs = {path: row for path, row in refs.items() if "/ziwei_column" not in path}
        rules = sorted(
            (row for row in refs.values() if row["kind"] == "rule"),
            key=lambda row: (not row["pointer"].startswith("/boundary_alerts/"), row["pointer"]),
        )
        for row in rules + [row for row in refs.values() if row["kind"] == "chart"]:
            pending = [refs[path] for path in row.get("evidence_pointers", [])] + [row]
            additions = {(item["document_id"], item["pointer"]): item for item in pending}
            if len(selected.keys() | additions.keys()) <= limit:
                selected.update(additions)
    return list(selected.values())


def _common(ctx: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": ctx.run_id,
        "epoch": ctx.epoch,
        "source_versions": snapshot["versions"],
        "source_ids": snapshot["source_ids"],
        "used_fact_ids": [row["id"] for row in snapshot["facts"]],
        "source_refs": [ref for row in snapshot["facts"] for ref in row.get("source_refs", [])],
    }


def _spec(ctx: Any, snapshot: dict[str, Any], reference: dict[str, Any], document: dict[str, Any]) -> tuple:
    kind = "artifact" if reference["kind"] == "chart" else "interpretive_claim"
    native = "p8-ref-" + fingerprint(reference)
    ident = "agent_p8_ref_" + fingerprint([ctx.owner, ctx.operation_id, native])[:32]
    content = dict(_common(ctx, snapshot), p8_reference=reference, p8_document_record=document)
    return kind, native, ident, content


def persist_reference_bundle(
    service: Any,
    ctx: Any,
    snapshot: dict[str, Any],
    documents: list[dict[str, Any]],
    *,
    system: str | None = None,
    limit: int = 10,
) -> dict:
    """Only trusted calculation callers supply documents; this is not an API."""
    with service.repo.transaction(ctx.owner):
        stored = persist_documents(service, ctx, snapshot, documents)
        indexed = {row["document_id"]: row for row in stored}
        result = {"documents": stored, "artifacts": [], "claims": [], "system": system, "limit": limit}
        for ref in selected_references(documents, system, limit):
            kind, native, ident, content = _spec(ctx, snapshot, ref, indexed[ref["document_id"]])
            row = service.repo.put(
                ctx.owner,
                kind,
                ident,
                content,
                subject=ctx.subject,
                expected_revision=0,
                operation_id=ctx.operation_id + ":" + native,
            )
            if row["status"] != "active":
                raise EvidenceError("P8引用已撤销，不得重新生成")
            result["artifacts" if kind == "artifact" else "claims"].append(
                {"id": ident, "native_id": native, "revision": row["revision"]}
            )
        return result


def verify_reference_bundle(
    service: Any, ctx: Any, snapshot: dict[str, Any], documents: list[dict], bundle: dict, *, system: str | None = None
) -> tuple:
    """Re-read exact native rows; completed-tool attestation stays with caller."""
    if ctx.private or ctx.crisis:
        raise ScopeError("当前模式不读取持久P8依据")
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        recheck_chart(service, ctx, snapshot)
        if (
            not isinstance(bundle, dict)
            or set(bundle) != {"documents", "artifacts", "claims", "system", "limit"}
            or (bundle["system"] != system or system not in (None, "bazi", "ziwei"))
        ):
            raise EvidenceError("P8引用清单无效")
        for group, identifier in (("documents", "document_id"), ("artifacts", "native_id"), ("claims", "native_id")):
            if not isinstance(bundle[group], list) or any(
                not isinstance(record, dict)
                or set(record) != {"id", identifier, "revision"}
                or type(record["revision"]) is not int
                or record["revision"] < 1
                for record in bundle[group]
            ):
                raise EvidenceError("P8持久记录需要精确整数修订")
        if len(bundle["documents"]) != len(documents):
            raise EvidenceError("P8文档清单不完整")
        versions, indexed = dict(snapshot["versions"]), {}
        for doc, record in zip(documents, bundle["documents"], strict=True):
            checked = verify_p8_document(
                doc["payload"],
                kind=doc["kind"],
                owner=ctx.owner,
                subject=ctx.subject,
                revision=snapshot["revision"],
                operation_id=ctx.operation_id,
                source_sha256=doc["source_sha256"],
            )
            if fingerprint(checked) != fingerprint(doc):
                raise EvidenceError("P8文档或Pointer清单已改变")
            expected_id = "agent_p8_" + fingerprint([ctx.owner, ctx.operation_id, doc["document_id"]])[:32]
            row = service.repo.get(ctx.owner, "artifact", expected_id, include_deleted=True)
            _active(row, record, ctx, expected_id)
            if service.repo.is_revoked(ctx.owner, "artifact", expected_id):
                raise EvidenceError("P8原文档已撤销")
            expected = dict(_common(ctx, snapshot), p8_document=doc)
            if any(fingerprint(row.get(key)) != fingerprint(value) for key, value in expected.items()):
                raise EvidenceError("P8文档持久内容不符")
            if record != {"id": expected_id, "revision": row["revision"], "document_id": doc["document_id"]}:
                raise EvidenceError("P8文档记录绑定不符")
            indexed[doc["document_id"]] = record
            versions[entity_dependency("artifact", expected_id)] = row["revision"]
        rows, expected_groups = [], {"artifacts": [], "claims": []}
        for ref in selected_references(documents, system, bundle["limit"]):
            kind, native, ident, content = _spec(ctx, snapshot, ref, indexed[ref["document_id"]])
            row = service.repo.get(ctx.owner, kind, ident, include_deleted=True)
            record = {"id": ident, "native_id": native, "revision": row["revision"]}
            _active(row, record, ctx, ident)
            if service.repo.is_revoked(ctx.owner, kind, ident):
                raise EvidenceError("P8引用已撤销")
            if any(fingerprint(row.get(key)) != fingerprint(value) for key, value in content.items()):
                raise EvidenceError("P8引用持久内容不符")
            expected_groups["artifacts" if kind == "artifact" else "claims"].append(record)
            versions[entity_dependency(kind, ident)] = row["revision"]
            rows.append(
                dict(
                    record,
                    kind=kind,
                    run_id=ctx.run_id,
                    epoch=ctx.epoch,
                    calculation_revision=snapshot["revision"],
                    basis="p8_validated_" + ref["kind"],
                    source_sha256=fingerprint(content),
                )
            )
        if any(fingerprint(bundle[key]) != fingerprint(expected_groups[key]) for key in expected_groups):
            raise EvidenceError("P8引用清单与本次文档不符")
        return rows, versions


def _active(row: dict, record: dict, ctx: Any, ident: str) -> None:
    if (
        row["status"] != "active"
        or row["subject_id"] != ctx.subject
        or row.get("run_id") != ctx.run_id
        or (type(row.get("epoch")) is not int or row["epoch"] != ctx.epoch)
    ):
        raise ScopeError("P8依据不属于本次有效运行")
    if record.get("id") != ident or type(record.get("revision")) is not int or record["revision"] != row["revision"]:
        raise RevisionConflict("P8依据修订已改变")

"""Additive v1.1 references; the 38 structural rules keep their own view."""

from __future__ import annotations

from .handoff_refs import reference, resolve
from .handoff_schema import CONTRACT_VERSION


def add_boundary_views(preview: dict, doc: dict) -> None:
    refs = [
        reference(doc, f"/boundary_alerts/{index}")
        for index in range(len(doc["payload"].get("boundary_alerts", [])))
    ]
    preview["view"]["boundary_alerts"] = refs
    preview["boundary_alerts"] = list(refs)


def boundary_binding(raw: dict, path: str) -> tuple[str, str]:
    alert = resolve(raw, path)
    charts = [
        row
        for row in raw["charts"]
        if row["time_basis"]["basis"] == "true_solar"
        and row["time_basis"]["instant_id"] == alert["instant_id"]
    ]
    if len(charts) != 1:
        raise ValueError("preview_boundary_primary_binding_missing")
    return charts[0]["id"], "true_solar"


def rule_evidence(doc: dict, path: str, hit: dict) -> tuple[str, list[dict]]:
    if path.startswith("/boundary_alerts/"):
        version, paths = hit["rules_version"], hit["evidence_paths"]
    else:
        prefix = "/".join(path.split("/")[:3])
        version = resolve(doc["payload"], prefix + "/data/p8/rules_version")
        paths = [prefix + value for value in hit["evidence_paths"]]
    return version, [reference(doc, value) for value in paths]


def rule_refs(preview: dict) -> list[dict]:
    return preview["view"]["rules"] + preview["view"].get("boundary_alerts", [])


def validate_boundary_views(preview: dict, docs: dict) -> None:
    current = preview["contract_version"] == CONTRACT_VERSION
    if (
        not current
        and "boundary_alerts" not in preview
        and "boundary_alerts" not in preview["view"]
    ):
        return
    basis_docs = [doc for doc in docs.values() if doc["kind"] == "time_basis"]
    if len(basis_docs) != 1:
        raise ValueError("preview_boundary_basis_document_required")
    doc = basis_docs[0]
    expected = [
        reference(doc, f"/boundary_alerts/{index}")
        for index in range(len(doc["payload"].get("boundary_alerts", [])))
    ]
    if (
        preview.get("boundary_alerts") != expected
        or preview["view"].get("boundary_alerts") != expected
    ):
        raise ValueError("preview_boundary_view_mismatch")
    for ref in expected:
        alert = resolve(doc["payload"], ref["path"])
        if alert.get("met") is not True or alert.get("critical") is not True:
            raise ValueError("preview_boundary_must_be_critical_hit")
        if (
            not alert.get("school")
            or not alert.get("source")
            or not alert.get("alternatives")
        ):
            raise ValueError("preview_boundary_provenance_required")
        boundary_binding(doc["payload"], ref["path"])

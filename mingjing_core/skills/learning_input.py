"""Verify content references for a caller-trusted chart handoff, without auth I/O."""

from __future__ import annotations

import re
from typing import Any

from ..adapters.charts.tool_evidence import content_hash, pointer
from ..domain.json_values import ensure_finite_json


def _same_scope(actual: dict, expected: dict) -> bool:
    return (
        isinstance(actual, dict)
        and set(actual) == set(expected)
        and all(
            type(actual[key]) is type(item) and actual[key] == item
            for key, item in expected.items()
        )
    )


def resolve_ref(documents: dict, ref: dict) -> Any:
    if not isinstance(ref, dict) or set(ref) != {"document_id", "path"}:
        raise ValueError("learning_reference_invalid")
    if ref["document_id"] not in documents:
        raise ValueError("learning_document_missing")
    data = documents[ref["document_id"]]["payload"]
    return data if ref["path"] == "" else pointer(data, ref["path"])


def _documents(value: dict) -> dict:
    documents = {}
    for doc in value["documents"]:
        content = {key: doc[key] for key in ("kind", "source_sha256", "payload")}
        expected = "doc-" + content_hash({"scope": value["scope"], **content})
        if doc["document_id"] != expected or expected in documents:
            raise ValueError("learning_document_hash_invalid")
        if doc["kind"] in ("time_basis", "western_timing"):
            if any(
                doc["payload"].get(key) != item
                or type(doc["payload"].get(key)) is not type(item)
                for key, item in value["scope"].items()
            ):
                raise ValueError("learning_document_scope_invalid")
        elif doc["kind"] != "calculation_bundle":
            raise ValueError("learning_document_kind_unsupported")
        else:
            for group in ("artifacts", "profiles", "features"):
                for item in doc["payload"][group].values():
                    if any(
                        item.get(key) != value["scope"][key]
                        or type(item.get(key)) is not type(value["scope"][key])
                        for key in ("owner_user_id", "subject_id", "revision")
                    ):
                        raise ValueError("learning_document_scope_invalid")
        documents[expected] = doc
    return documents


def _binding(documents: dict, ref: dict) -> tuple[str, str]:
    doc, path = documents[ref["document_id"]], ref["path"]
    if doc["kind"] == "time_basis":
        raw = doc["payload"]
        if path.startswith("/charts/"):
            chart = pointer(raw, "/".join(path.split("/")[:3]))
            return chart["id"], chart["time_basis"]["basis"]
        if path.startswith("/boundary_alerts/"):
            hit = pointer(raw, path)
            charts = [
                row
                for row in raw["charts"]
                if row["time_basis"]["basis"] == "true_solar"
                and row["time_basis"]["instant_id"] == hit["instant_id"]
            ]
            if len(charts) != 1:
                raise ValueError("learning_boundary_branch_invalid")
            return charts[0]["id"], "true_solar"
        valid = [
            row for row in raw["time_basis"]["instants"] if row["status"] == "valid"
        ]
        if len(valid) != 1:
            raise ValueError("learning_physical_instant_ambiguous")
        return valid[0]["id"], "actual_UTC"
    bundles = [
        row["payload"]
        for row in documents.values()
        if row["kind"] == "calculation_bundle"
    ]
    if len(bundles) != 1 or len(bundles[0]["artifacts"]) != 1:
        raise ValueError("learning_astro_bundle_ambiguous")
    return next(iter(bundles[0]["artifacts"].values()))["branch_id"], "actual_UTC"


def _aliases(value: dict, documents: dict) -> dict:
    aliases = {}
    for prefix in ("c", "r"):
        for row in value["aliases"][prefix]:
            name = row["alias"]
            if not re.fullmatch(prefix + r"[1-9][0-9]*", name) or name in aliases:
                raise ValueError("learning_alias_invalid")
            actual = resolve_ref(documents, row["ref"])
            fields = ("scope", "ref", "value_sha256", "branch_id", "basis")
            claim = {key: row[key] for key in fields}
            claim.update(
                {key: row[key] for key in ("rule_id", "rules_version") if key in row}
            )
            if not _same_scope(row["scope"], value["scope"]) or row[
                "value_sha256"
            ] != content_hash(actual):
                raise ValueError("learning_alias_content_invalid")
            if row["claim_id"] != "demo-claim-" + content_hash(claim):
                raise ValueError("learning_alias_claim_invalid")
            branch, basis = _binding(documents, row["ref"])
            if row["branch_id"] != branch or row["basis"] != basis:
                raise ValueError("learning_alias_branch_invalid")
            if prefix == "r" and (
                actual.get("met") is not True or actual.get("rule_id") != row["rule_id"]
            ):
                raise ValueError("learning_rule_must_be_true")
            aliases[name] = row
    for row in value["aliases"]["r"]:
        if not row["evidence_aliases"] or any(
            name not in aliases or not name.startswith("c")
            for name in row["evidence_aliases"]
        ):
            raise ValueError("learning_rule_evidence_missing")
        _rule_provenance(row, documents, aliases)
    return aliases


def _rule_provenance(row: dict, documents: dict, aliases: dict) -> None:
    ref = row["ref"]
    doc = documents[ref["document_id"]]["payload"]
    hit = resolve_ref(documents, ref)
    if ref["path"].startswith("/boundary_alerts/"):
        paths, version = hit["evidence_paths"], hit["rules_version"]
        candidates = [
            chart
            for chart in doc["charts"]
            if chart["time_basis"]["basis"] == "true_solar"
            and chart["time_basis"]["instant_id"] == hit["instant_id"]
        ]
        if len(candidates) != 1:
            raise ValueError("learning_boundary_branch_invalid")
        chart = candidates[0]
    elif "/data/p8/rule_hits/" in ref["path"]:
        prefix = "/".join(ref["path"].split("/")[:3])
        chart = pointer(doc, prefix)
        paths = [prefix + path for path in hit["evidence_paths"]]
        version = chart["data"]["p8"]["rules_version"]
    else:
        raise ValueError("learning_rule_path_invalid")
    expected = [{"document_id": ref["document_id"], "path": path} for path in paths]
    actual = [aliases[name]["ref"] for name in row["evidence_aliases"]]
    if actual != expected or row["rules_version"] != version:
        raise ValueError("learning_rule_provenance_invalid")
    if row["branch_id"] != chart["id"] or row["basis"] != chart["time_basis"]["basis"]:
        raise ValueError("learning_rule_branch_invalid")


def verified_input(value: dict) -> tuple[dict, dict]:
    """Content hashes are not signatures; caller still owns authorization and origin trust."""
    ensure_finite_json(value)
    if not isinstance(value, dict) or value.get("contract_version") not in (
        "p8-chart-compute-preview-v1",
        "p8-chart-compute-preview-v1.1",
    ):
        raise ValueError("learning_contract_unsupported")
    try:
        scope = value["scope"]
        if set(scope) != {"owner_user_id", "subject_id", "operation_id", "revision"}:
            raise ValueError("learning_scope_invalid")
        if (
            type(scope["revision"]) is not int
            or scope["revision"] < 0
            or any(
                not isinstance(scope[key], str) or not scope[key].strip()
                for key in ("owner_user_id", "subject_id", "operation_id")
            )
        ):
            raise ValueError("learning_scope_invalid")
        documents = _documents(value)
        aliases = _aliases(value, documents)
        _primary_view(value, documents)
        for refs in value["view"].values():
            for ref in refs:
                resolve_ref(documents, ref)
        return documents, aliases
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("learning_input_invalid") from exc


def _primary_view(value: dict, documents: dict) -> None:
    system = value["request"]["system"]
    if system not in ("bazi", "ziwei", "astro"):
        raise ValueError("learning_system_unsupported")
    expected = []
    for ident, doc in documents.items():
        if system == "astro" and doc["kind"] == "calculation_bundle":
            expected += [
                {"document_id": ident, "path": f"/artifacts/{key}/data"}
                for key, row in doc["payload"]["artifacts"].items()
                if row["system"] == "astro"
            ]
        elif system != "astro" and doc["kind"] == "time_basis":
            for index, chart in enumerate(doc["payload"]["charts"]):
                is_primary = chart["time_basis"]["basis"] == "true_solar"
                if (chart["interpretation_role"] == "primary") != is_primary:
                    raise ValueError("learning_native_primary_invalid")
                if is_primary:
                    leaf = "data" if system == "bazi" else "ziwei_column"
                    expected.append(
                        {"document_id": ident, "path": f"/charts/{index}/{leaf}"}
                    )
    if value["view"]["primary"] != expected:
        raise ValueError("learning_primary_view_invalid")

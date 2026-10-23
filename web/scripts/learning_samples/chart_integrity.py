"""Read-only content/branch checks for the caller-held chart preview envelope.

Integrity is not an authorization or origin signature. Never export these raw
payloads, scope fields or the generic Pointer resolver to a browser.
"""

from __future__ import annotations

import math
import re

from .common import digest, need, pointer, same

ERROR = "learning_public_projection_invalid"
ERRORS = (KeyError, TypeError, IndexError, AttributeError, ValueError, OverflowError, RecursionError)
SCOPE_KEYS = {"owner_user_id", "subject_id", "revision", "operation_id"}
CHART_KEYS = {"alias", "claim_id", "scope", "ref", "value_sha256", "branch_id", "basis"}
RULE_KEYS = CHART_KEYS | {"rule_id", "rules_version", "evidence_aliases"}
VIEW_KEYS = {
    "time_basis",
    "primary",
    "comparisons",
    "diagnostics",
    "rules",
    "assessments",
    "interactions",
    "flying",
    "transits",
    "timings",
}
BASES = {"true_solar", "standard", "beijing_standard", "actual_UTC"}


def _finite(value: object) -> None:
    kind = type(value)
    if kind in (type(None), str, bool, int):
        return
    if kind is float:
        need(math.isfinite(value))
    elif kind is list:
        for item in value:
            _finite(item)
    elif kind is dict:
        need(all(type(key) is str for key in value))
        for item in value.values():
            _finite(item)
    else:
        need(False)


def _nonempty(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _scope(value: object) -> dict:
    need(type(value) is dict and set(value) == SCOPE_KEYS)
    need(type(value["revision"]) is int and value["revision"] >= 0)
    need(all(_nonempty(value[key]) for key in SCOPE_KEYS - {"revision"}))
    return value


def resolve_ref(documents: dict, ref: dict) -> object:
    try:
        need(type(ref) is dict and set(ref) == {"document_id", "path"})
        need(type(ref["document_id"]) is str and ref["document_id"] in documents)
        need(type(ref["path"]) is str and (ref["path"] == "" or ref["path"].startswith("/")))
        document = documents[ref["document_id"]]
        need(type(document) is dict and "payload" in document)
        return document["payload"] if ref["path"] == "" else pointer(document["payload"], ref["path"])
    except ERRORS:
        raise ValueError(ERROR) from None


def _documents(value: dict) -> dict[str, dict]:
    need(type(value["documents"]) is list and bool(value["documents"]))
    documents = {}
    for row in value["documents"]:
        need(type(row) is dict and set(row) == {"document_id", "kind", "source_sha256", "payload"})
        sources = row["source_sha256"]
        need(type(sources) is dict and bool(sources))
        need(
            all(
                _nonempty(key) and type(sha) is str and re.fullmatch(r"[a-f0-9]{64}", sha)
                for key, sha in sources.items()
            )
        )
        content = {key: row[key] for key in ("kind", "source_sha256", "payload")}
        expected = "doc-" + digest({"scope": value["scope"], **content})
        need(row["document_id"] == expected and expected not in documents)
        raw = row["payload"]
        need(type(raw) is dict)
        if row["kind"] in ("time_basis", "western_timing"):
            need(all(key in raw and same(raw[key], item) for key, item in value["scope"].items()))
        else:
            need(row["kind"] == "calculation_bundle")
            for group in ("artifacts", "profiles", "features"):
                need(type(raw[group]) is dict)
                for item in raw[group].values():
                    need(type(item) is dict)
                    need(
                        all(
                            key in item and same(item[key], value["scope"][key])
                            for key in ("owner_user_id", "subject_id", "revision")
                        )
                    )
        documents[expected] = row
    return documents


def _physical_binding(raw: dict) -> tuple[str, str]:
    need(type(raw["time_basis"]["instants"]) is list)
    valid = [row for row in raw["time_basis"]["instants"] if row["status"] == "valid"]
    need(len(valid) == 1 and _nonempty(valid[0]["id"]))
    return valid[0]["id"], "actual_UTC"


def _binding(documents: dict, ref: dict) -> tuple[str, str]:
    document, path = documents[ref["document_id"]], ref["path"]
    raw = document["payload"]
    if document["kind"] == "time_basis":
        if path.startswith("/charts/"):
            chart = pointer(raw, "/".join(path.split("/")[:3]))
            need(type(chart) is dict and _nonempty(chart["id"]))
            need(chart["time_basis"]["basis"] in BASES)
            return chart["id"], chart["time_basis"]["basis"]
        if path.startswith("/boundary_alerts/"):
            hit = resolve_ref(documents, ref)
            candidates = [
                chart
                for chart in raw["charts"]
                if chart["time_basis"]["basis"] == "true_solar"
                and chart["time_basis"]["instant_id"] == hit["instant_id"]
            ]
            need(len(candidates) == 1 and _nonempty(candidates[0]["id"]))
            return candidates[0]["id"], "true_solar"
        return _physical_binding(raw)
    bundles = [row["payload"] for row in documents.values() if row["kind"] == "calculation_bundle"]
    need(len(bundles) == 1 and len(bundles[0]["artifacts"]) == 1)
    artifact = next(iter(bundles[0]["artifacts"].values()))
    need(_nonempty(artifact["branch_id"]))
    return artifact["branch_id"], "actual_UTC"


def _alias_row(row: dict, prefix: str, value: dict, documents: dict) -> object:
    keys = CHART_KEYS if prefix == "c" else RULE_KEYS
    need(type(row) is dict and set(row) == keys)
    need(type(row["alias"]) is str and re.fullmatch(prefix + r"[1-9][0-9]*", row["alias"]))
    need(same(_scope(row["scope"]), value["scope"]))
    need(_nonempty(row["branch_id"]) and row["basis"] in BASES)
    actual = resolve_ref(documents, row["ref"])
    need(type(row["value_sha256"]) is str and row["value_sha256"] == digest(actual))
    claim = {key: row[key] for key in ("scope", "ref", "value_sha256", "branch_id", "basis")}
    if prefix == "r":
        need(_nonempty(row["rule_id"]) and _nonempty(row["rules_version"]))
        claim.update({key: row[key] for key in ("rule_id", "rules_version")})
    need(row["claim_id"] == "demo-claim-" + digest(claim))
    branch, basis = _binding(documents, row["ref"])
    need(row["branch_id"] == branch and row["basis"] == basis)
    if prefix == "r":
        need(type(actual) is dict and actual.get("met") is True and actual.get("rule_id") == row["rule_id"])
    return actual


def _rule_provenance(row: dict, documents: dict, aliases: dict) -> None:
    ref = row["ref"]
    raw = documents[ref["document_id"]]["payload"]
    hit = resolve_ref(documents, ref)
    need(type(hit["evidence_paths"]) is list and bool(hit["evidence_paths"]))
    need(all(type(path) is str and path.startswith("/") for path in hit["evidence_paths"]))
    if ref["path"].startswith("/boundary_alerts/"):
        need(re.fullmatch(r"/boundary_alerts/(0|[1-9][0-9]*)", ref["path"]) is not None)
        paths, version = hit["evidence_paths"], hit["rules_version"]
        candidates = [
            chart
            for chart in raw["charts"]
            if chart["time_basis"]["basis"] == "true_solar" and chart["time_basis"]["instant_id"] == hit["instant_id"]
        ]
        need(len(candidates) == 1)
        chart = candidates[0]
    else:
        need(re.fullmatch(r"/charts/(0|[1-9][0-9]*)/data/p8/rule_hits/(0|[1-9][0-9]*)", ref["path"]) is not None)
        prefix = "/".join(ref["path"].split("/")[:3])
        chart = pointer(raw, prefix)
        need(chart["time_basis"]["basis"] == "true_solar" and chart["interpretation_role"] == "primary")
        need(all(path.startswith("/data/") for path in hit["evidence_paths"]))
        paths = [prefix + path for path in hit["evidence_paths"]]
        version = chart["data"]["p8"]["rules_version"]
    expected = [{"document_id": ref["document_id"], "path": path} for path in paths]
    actual = [aliases[name]["ref"] for name in row["evidence_aliases"]]
    need(same(actual, expected) and row["rules_version"] == version)
    need(row["branch_id"] == chart["id"] and row["basis"] == chart["time_basis"]["basis"])


def _aliases(value: dict, documents: dict) -> dict[str, dict]:
    need(type(value["aliases"]) is dict and set(value["aliases"]) == {"c", "r"})
    aliases = {}
    for prefix in ("c", "r"):
        need(type(value["aliases"][prefix]) is list)
        for row in value["aliases"][prefix]:
            _alias_row(row, prefix, value, documents)
            need(row["alias"] not in aliases)
            aliases[row["alias"]] = row
    for row in value["aliases"]["r"]:
        names = row["evidence_aliases"]
        need(type(names) is list and bool(names))
        need(all(type(name) is str and name.startswith("c") and name in aliases for name in names))
        _rule_provenance(row, documents, aliases)
    return aliases


def _primary(value: dict, documents: dict, system: str) -> None:
    expected = []
    for ident, document in documents.items():
        raw = document["payload"]
        if system == "astro" and document["kind"] == "calculation_bundle":
            expected.extend(
                {"document_id": ident, "path": f"/artifacts/{key}/data"}
                for key, row in raw["artifacts"].items()
                if row["system"] == "astro"
            )
        elif system != "astro" and document["kind"] == "time_basis":
            need(type(raw["charts"]) is list)
            for index, chart in enumerate(raw["charts"]):
                is_primary = chart["time_basis"]["basis"] == "true_solar"
                need((chart["interpretation_role"] == "primary") is is_primary)
                if is_primary:
                    leaf = "data" if system == "bazi" else "ziwei_column"
                    expected.append({"document_id": ident, "path": f"/charts/{index}/{leaf}"})
    need(same(value["view"]["primary"], expected))


def _views(value: dict, documents: dict, system: str) -> None:
    view = value["view"]
    need(type(view) is dict)
    keys = VIEW_KEYS | ({"boundary_alerts"} if "boundary_alerts" in view else set())
    need(set(view) == keys)
    for refs in view.values():
        need(type(refs) is list)
        for ref in refs:
            resolve_ref(documents, ref)
    if value["contract_version"] == "p8-chart-compute-preview-v1.1":
        need("boundary_alerts" in view and same(value["boundary_alerts"], view["boundary_alerts"]))
    _primary(value, documents, system)


def verify_chart(value: dict, system: str) -> tuple[dict[str, dict], dict[str, dict]]:
    try:
        _finite(value)
        need(type(value) is dict and system in {"bazi", "ziwei", "astro"})
        need(value["contract_version"] in {"p8-chart-compute-preview-v1", "p8-chart-compute-preview-v1.1"})
        need(value["mode"] == "scripted_synthetic_preview" and value["status"] == "draft_integration_contract")
        need(type(value["request"]) is dict and value["request"]["system"] == system)
        _scope(value["scope"])
        need(same(value["effects"], {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_demo_only"}))
        documents = _documents(value)
        aliases = _aliases(value, documents)
        _views(value, documents, system)
        return documents, aliases
    except ERRORS:
        raise ValueError(ERROR) from None

"""Structural plus semantic checks for offline handoff fixtures, never an API."""

from __future__ import annotations

from datetime import timedelta

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from ....domain.json_values import ensure_finite_json
from .handoff_refs import claim_id, digest, document_id, resolve
from .handoff_schema import schema
from .handoff_validate_data import native_document, same_scope, utc


def _documents(preview: dict, verify_runtime_sources: bool) -> dict:
    docs = {}
    for doc in preview["documents"]:
        ident = doc["document_id"]
        if ident in docs:
            raise ValueError("preview_duplicate_document")
        expected = document_id(
            preview["scope"], doc["kind"], doc["source_sha256"], doc["payload"]
        )
        if ident != expected:
            raise ValueError("preview_document_hash_mismatch")
        native_document(doc, preview)
        if verify_runtime_sources:
            from ..p8_worker import source_hashes

            if doc["source_sha256"] != source_hashes():
                raise ValueError("preview_runtime_source_mismatch")
        docs[ident] = doc
    if len({digest(doc["source_sha256"]) for doc in docs.values()}) != 1:
        raise ValueError("preview_source_snapshot_mismatch")
    return docs


def _value(docs: dict, ref: dict):
    if ref["document_id"] not in docs:
        raise ValueError("preview_dangling_document_ref")
    return resolve(docs[ref["document_id"]]["payload"], ref["path"])


def _binding(preview: dict, doc: dict, path: str) -> tuple[str, str]:
    if doc["kind"] == "time_basis":
        if path.startswith("/charts/"):
            parts = path.split("/")
            chart = resolve(doc["payload"], "/".join(parts[:3]))
            return chart["id"], chart["time_basis"]["basis"]
        valid = [
            row
            for row in doc["payload"]["time_basis"]["instants"]
            if row["status"] == "valid"
        ]
        return valid[0]["id"], "actual_UTC"
    bundles = [
        row["payload"]
        for row in preview["documents"]
        if row["kind"] == "calculation_bundle"
    ]
    if len(bundles) != 1:
        raise ValueError("preview_astro_branch_bundle_required")
    artifact = next(iter(bundles[0]["artifacts"].values()))
    return artifact["branch_id"], "actual_UTC"


def _aliases(preview: dict, docs: dict) -> dict:
    lookup, identities = {}, set()
    for prefix in ("c", "r"):
        for index, row in enumerate(preview["aliases"][prefix], 1):
            if row["alias"] != f"{prefix}{index}" or row["alias"] in lookup:
                raise ValueError("preview_alias_sequence_invalid")
            same_scope(preview["scope"], row["scope"], operation=True)
            value = _value(docs, row["ref"])
            doc = docs[row["ref"]["document_id"]]
            if digest(value) != row["value_sha256"] or claim_id(row) != row["claim_id"]:
                raise ValueError("preview_claim_hash_mismatch")
            branch, basis = _binding(preview, doc, row["ref"]["path"])
            if row["branch_id"] != branch or row["basis"] != basis:
                raise ValueError("preview_alias_branch_or_basis_mismatch")
            identity = (prefix, row["ref"]["document_id"], row["ref"]["path"])
            if identity in identities:
                raise ValueError("preview_duplicate_alias_reference")
            identities.add(identity)
            lookup[row["alias"]] = row
    return lookup


def _rules(preview: dict, docs: dict, aliases: dict) -> None:
    expected_hits = {
        (row["document_id"], row["path"]) for row in preview["view"]["rules"]
    }
    actual_hits = set()
    for row in preview["aliases"]["r"]:
        ref = row["ref"]
        hit = _value(docs, ref)
        path, ident = ref["path"], ref["document_id"]
        if (
            "/data/p8/rule_hits/" not in path
            or hit.get("met") is not True
            or row["rule_id"] != hit.get("rule_id")
        ):
            raise ValueError("preview_rule_must_reference_true_hit")
        prefix = "/".join(path.split("/")[:3])
        version = resolve(docs[ident]["payload"], prefix + "/data/p8/rules_version")
        if row["rules_version"] != version:
            raise ValueError("preview_rule_version_mismatch")
        expected = [
            {"document_id": ident, "path": prefix + item}
            for item in hit["evidence_paths"]
        ]
        if not expected or len(set(row["evidence_aliases"])) != len(expected):
            raise ValueError("preview_rule_evidence_count_mismatch")
        evidence = []
        for name in row["evidence_aliases"]:
            if name not in aliases or not name.startswith("c"):
                raise ValueError("preview_rule_evidence_alias_missing")
            source = aliases[name]
            if (
                source["branch_id"] != row["branch_id"]
                or source["basis"] != row["basis"]
            ):
                raise ValueError("preview_rule_evidence_branch_mismatch")
            evidence.append(source["ref"])
        if evidence != expected:
            raise ValueError("preview_rule_evidence_pointer_mismatch")
        actual_hits.add((ident, path))
    if actual_hits != expected_hits:
        raise ValueError("preview_rule_alias_coverage_mismatch")


def _basis_view(preview: dict, docs: dict) -> None:
    system = preview["request"]["system"]
    leaf = "data" if system == "bazi" else "ziwei_column"
    expected = {
        key: []
        for key in (
            "time_basis",
            "primary",
            "comparisons",
            "diagnostics",
            "rules",
            "assessments",
            "interactions",
            "flying",
        )
    }
    basis_docs = [doc for doc in docs.values() if doc["kind"] == "time_basis"]
    if len(basis_docs) != 1 or len(docs) != 1:
        raise ValueError("preview_single_basis_document_required")
    for doc in docs.values():
        ident = doc["document_id"]
        expected["time_basis"].append({"document_id": ident, "path": "/time_basis"})
        for index, chart in enumerate(doc["payload"]["charts"]):
            group = {
                "primary": "primary",
                "comparison": "comparisons",
                "diagnostic": "diagnostics",
            }[chart["interpretation_role"]]
            path = f"/charts/{index}/{leaf}"
            expected[group].append({"document_id": ident, "path": path})
            if group == "primary":
                _basis_details(expected, chart, ident, path, system)
    if any(preview["view"][key] != value for key, value in expected.items()):
        raise ValueError("preview_basis_view_mismatch")
    if system == "ziwei" and (preview["view"]["rules"] or preview["aliases"]["r"]):
        raise ValueError("preview_no_unimplemented_ziwei_rules")


def _basis_details(
    expected: dict, chart: dict, ident: str, path: str, system: str
) -> None:
    if system == "ziwei":
        expected["flying"].append(
            {"document_id": ident, "path": path + "/p8_flying_transformations"}
        )
        return
    p8 = chart["data"]["p8"]
    expected["rules"] += [
        {"document_id": ident, "path": path + f"/p8/rule_hits/{index}"}
        for index in range(len(p8["rule_hits"]))
    ]
    for key, field in (
        ("assessments", "rule_assessments"),
        ("interactions", "time_interactions"),
    ):
        expected[key].append({"document_id": ident, "path": path + "/p8/" + field})


def _astro_view(preview: dict, docs: dict) -> None:
    if preview["view"]["rules"] or preview["aliases"]["r"]:
        raise ValueError("preview_no_unimplemented_astro_rules")
    _astro_refs(preview, docs)
    timings = [_value(docs, ref) for ref in preview["view"]["timings"]]
    if {row["version"] for row in timings} != {
        "p8-secondary-progressions-v1",
        "p8-solar-return-v1",
    }:
        raise ValueError("preview_named_timings_required")
    physical = utc(preview["request"]["physical_birth_at_utc"])
    if any(utc(row["actual_UTC"]["birth_at"]) != physical for row in timings):
        raise ValueError("preview_astro_actual_utc_mismatch")
    transits = [_value(docs, ref) for ref in preview["view"]["transits"]]
    if len(transits) != 1:
        raise ValueError("preview_explicit_transit_interval_required")
    interval = transits[0]["actual_UTC"]
    start, end = utc(interval["start_at"]), utc(interval["end_at"])
    if (
        end - start != timedelta(days=7)
        or start.date().isoformat() != preview["request"]["target_date"]
    ):
        raise ValueError("preview_seven_day_interval_required")


def _astro_refs(preview: dict, docs: dict) -> None:
    bundles = [doc for doc in docs.values() if doc["kind"] == "calculation_bundle"]
    bases = [doc for doc in docs.values() if doc["kind"] == "time_basis"]
    timings = [doc for doc in docs.values() if doc["kind"] == "western_timing"]
    if len(bundles) != 1 or len(bases) != 1 or len(timings) != 2:
        raise ValueError("preview_astro_documents_incomplete")
    bundle = bundles[0]
    artifact = next(iter(bundle["payload"]["artifacts"]))
    prefix = f"/artifacts/{artifact}/data"
    expected = {key: [] for key in preview["view"]}
    expected["time_basis"] = [
        {"document_id": bases[0]["document_id"], "path": "/time_basis/instants/0"}
    ]
    expected["primary"] = [{"document_id": bundle["document_id"], "path": prefix}]
    expected["transits"] = [
        {"document_id": bundle["document_id"], "path": prefix + "/p8_transit_windows"}
    ]
    expected["timings"] = [
        {"document_id": doc["document_id"], "path": "/data"} for doc in timings
    ]
    if preview["view"] != expected:
        raise ValueError("preview_astro_view_binding_mismatch")


def validate_preview(value: dict, *, verify_runtime_sources: bool = False) -> None:
    """Validate a local preview; optional current-source checks need this checkout."""
    ensure_finite_json(value)
    try:
        Draft202012Validator(schema(), format_checker=FormatChecker()).validate(value)
    except ValidationError as exc:
        raise ValueError("preview_schema_invalid") from exc
    try:
        docs = _documents(value, verify_runtime_sources)
        for group in value["view"].values():
            for ref in group:
                _value(docs, ref)
        aliases = _aliases(value, docs)
        _view_alias_coverage(value)
        _rules(value, docs, aliases)
        if value["request"]["system"] == "astro":
            _astro_view(value, docs)
        else:
            _basis_view(value, docs)
    except (KeyError, TypeError, IndexError, AttributeError, StopIteration) as exc:
        raise ValueError("preview_native_payload_invalid") from exc


def _view_alias_coverage(preview: dict) -> None:
    chart_refs = {
        (row["ref"]["document_id"], row["ref"]["path"])
        for row in preview["aliases"]["c"]
    }
    expected = {
        (ref["document_id"], ref["path"])
        for group in preview["view"].values()
        for ref in group
    }
    if not expected <= chart_refs:
        raise ValueError("preview_view_alias_missing")

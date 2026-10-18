"""Check native provenance and scope without changing a source payload."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from .handoff_refs import digest, resolve


def same_scope(scope: dict, value: dict, *, operation: bool = False) -> None:
    keys = ["owner_user_id", "subject_id", "revision"]
    if operation:
        keys.append("operation_id")
    if any(
        value.get(key) != scope[key] or type(value.get(key)) is not type(scope[key])
        for key in keys
    ):
        raise ValueError("preview_scope_mismatch")


def utc(value: str) -> datetime:
    point = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if point.tzinfo is None or point.utcoffset() != timedelta():
        raise ValueError("preview_actual_utc_required")
    return point.astimezone(UTC)


def _basis(doc: dict, preview: dict) -> None:
    raw, request = doc["payload"], preview["request"]
    same_scope(preview["scope"], raw, operation=True)
    if raw["source_sha256"] != doc["source_sha256"]:
        raise ValueError("preview_source_hash_mismatch")
    valid = [row for row in raw["time_basis"]["instants"] if row["status"] == "valid"]
    if len(valid) != 1 or raw["time_basis"]["requires_confirmation"]:
        raise ValueError("preview_ambiguous_physical_instant")
    instant = valid[0]
    if utc(instant["utc"]) != utc(request["physical_birth_at_utc"]):
        raise ValueError("preview_birth_utc_mismatch")
    reported = request["birth"]["date"] + "T" + request["birth"]["reported_time"]
    if datetime.fromisoformat(instant["reported"]) != datetime.fromisoformat(reported):
        raise ValueError("preview_birth_report_mismatch")
    if instant["timezone"] != request["birth"]["place"]["tz"]:
        raise ValueError("preview_birth_timezone_mismatch")
    primary = [
        row for row in raw["charts"] if row["time_basis"]["basis"] == "true_solar"
    ]
    if not primary or raw["time_basis"]["selected_basis"] != "true_solar":
        raise ValueError("preview_true_solar_primary_required")
    if raw["interpretation"]["primary_chart_ids"] != [row["id"] for row in primary]:
        raise ValueError("preview_primary_chart_binding_mismatch")
    for row in raw["charts"]:
        candidate = row["time_basis"]
        if (
            utc(candidate["utc"]) != utc(instant["utc"])
            or candidate["instant_id"] != instant["id"]
        ):
            raise ValueError("preview_chart_instant_mismatch")
        if candidate["solar_time"]["longitude"] != request["birth"]["place"]["lon"]:
            raise ValueError("preview_birth_longitude_mismatch")
        _chart_evidence(row, raw)
    if raw["model_calls"] != 0 or raw["writes"] != 0 or raw["profile_update_allowed"]:
        raise ValueError("preview_native_effects_forbidden")


def _chart_evidence(chart: dict, raw: dict) -> None:
    p8 = chart["data"]["p8"]
    assessments = p8["rule_assessments"]
    if p8["rule_hits"] != [row for row in assessments if row["met"] is True]:
        raise ValueError("preview_hit_assessment_mismatch")
    for row in assessments:
        if type(row["met"]) is not bool:
            raise ValueError("preview_rule_met_must_be_boolean")
        for path in row["evidence_paths"]:
            resolve({"data": chart["data"]}, path)
    expected = (
        "primary" if chart["time_basis"]["basis"] == "true_solar" else "diagnostic"
    )
    if any(
        item["comparison_chart_id"] == chart["id"]
        for item in raw["interpretation"]["comparisons"]
    ):
        expected = "comparison"
    if chart["interpretation_role"] != expected or chart["visible_by_default"] != (
        expected != "diagnostic"
    ):
        raise ValueError("preview_native_interpretation_role_mismatch")
    _pointer_tree(chart["ziwei_column"]["p8_flying_transformations"], raw)


def _pointer_tree(value, root: dict) -> None:
    if isinstance(value, list):
        for child in value:
            _pointer_tree(child, root)
    elif isinstance(value, dict):
        for key, child in value.items():
            if key.endswith("_pointer") and isinstance(child, str):
                resolve(root, child)
            elif key == "evidence_paths":
                for path in child:
                    resolve(root, path)
            else:
                _pointer_tree(child, root)


def _profile_utc(profile: dict, expected: str) -> None:
    values = profile["input"]
    offset = timedelta(hours=values["timezone_offset"])
    point = datetime.fromisoformat(values["sample_civil_datetime"]).replace(
        tzinfo=timezone(offset)
    )
    if point.astimezone(UTC) != utc(expected):
        raise ValueError("preview_calculation_birth_utc_mismatch")


def _bundle(doc: dict, preview: dict) -> None:
    raw, scope = doc["payload"], preview["scope"]
    if raw["errors"] or len(raw["artifacts"]) != 1:
        raise ValueError("preview_successful_single_astro_bundle_required")
    branches = {row["id"]: row for row in raw["branches"]}
    for row in branches.values():
        same_scope(scope, row)
    for key, profile in raw["profiles"].items():
        same_scope(scope, profile)
        if (
            key != profile["id"]
            or profile["versions"]["p8"]["source_sha256"] != doc["source_sha256"]
        ):
            raise ValueError("preview_profile_source_binding_mismatch")
        _profile_utc(profile, preview["request"]["physical_birth_at_utc"])
    for key, artifact in raw["artifacts"].items():
        same_scope(scope, artifact)
        profile = raw["profiles"][artifact["profile_id"]]
        if (
            artifact["system"] != "astro"
            or key != artifact["id"]
            or artifact["branch_id"] not in branches
        ):
            raise ValueError("preview_artifact_binding_mismatch")
        if (
            profile["branch_id"] != artifact["branch_id"]
            or artifact["target_date"] != preview["request"]["target_date"]
        ):
            raise ValueError("preview_artifact_profile_mismatch")
    for key, feature in raw["features"].items():
        same_scope(scope, feature)
        artifact = raw["artifacts"][feature["artifact_id"]]
        if key != feature["id"] or feature["branch_id"] != artifact["branch_id"]:
            raise ValueError("preview_feature_binding_mismatch")
        if digest(feature["value"]) != digest(resolve(artifact, feature["path"])):
            raise ValueError("preview_feature_value_mismatch")


def _timing(doc: dict, preview: dict) -> None:
    raw = doc["payload"]
    same_scope(preview["scope"], raw, operation=True)
    if (
        raw["source_sha256"] != doc["source_sha256"]
        or raw["time_basis"] != "actual_UTC_not_true_solar"
    ):
        raise ValueError("preview_timing_source_or_basis_mismatch")
    if utc(raw["data"]["actual_UTC"]["birth_at"]) != utc(
        preview["request"]["physical_birth_at_utc"]
    ):
        raise ValueError("preview_timing_birth_utc_mismatch")
    if raw["model_calls"] != 0 or raw["writes"] != 0 or raw["profile_update_allowed"]:
        raise ValueError("preview_native_effects_forbidden")


def native_document(doc: dict, preview: dict) -> None:
    handlers = {
        "time_basis": _basis,
        "calculation_bundle": _bundle,
        "western_timing": _timing,
    }
    try:
        handlers[doc["kind"]](doc, preview)
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("preview_native_payload_invalid") from exc

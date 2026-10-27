"""Strict participant view: no target item or answer-key hints may accompany a case."""

import re

from .models import CalibrationError, digest, fingerprint, identity

BLIND_PAYLOAD_SCHEMA = "blind-review-batch-v3.1"


def blind_payload_digest(value: object) -> str:
    allowed = {
        "schema",
        "batch_id",
        "ordinal",
        "plan_sha256",
        "rubric_sha256",
        "owner_id",
        "reviewer_id",
        "common_material",
        "candidates",
    }
    if type(value) is not dict or set(value) != allowed or value["schema"] != BLIND_PAYLOAD_SCHEMA:
        raise CalibrationError("blind_payload_shape_invalid")
    for name in ("batch_id", "owner_id", "reviewer_id"):
        identity(value[name])
    for name in ("plan_sha256", "rubric_sha256"):
        digest(value[name])
    if type(value["ordinal"]) is not int or not 1 <= value["ordinal"] <= 5:
        raise CalibrationError("blind_payload_ordinal_invalid")
    if type(value["common_material"]) is not str or not value["common_material"].strip():
        raise CalibrationError("blind_common_material_required")
    candidates = value["candidates"]
    if type(candidates) is not list or len(candidates) != 15:
        raise CalibrationError("blind_fifteen_candidates_required")
    for candidate in candidates:
        if type(candidate) is not dict or set(candidate) != {"id", "material", "user", "draft"}:
            raise CalibrationError("blind_candidate_fields_invalid")
        if type(candidate["id"]) is not str or re.fullmatch(r"b_[a-f0-9]{32}", candidate["id"]) is None:
            raise CalibrationError("blind_candidate_id_invalid")
        if any(
            type(candidate[name]) is not str or not candidate[name].strip() for name in ("material", "user", "draft")
        ):
            raise CalibrationError("blind_candidate_content_missing")
    if len({candidate["id"] for candidate in candidates}) != 15:
        raise CalibrationError("blind_candidate_duplicate")
    return fingerprint(value)

"""Public core4 envelope, with legacy read projections and no private model fields."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from mingjing_core.agent.event_contracts import Asked, EnvelopeV1
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.domain.json_values import ensure_finite_json
from mingjing_core.validation.structural import StructuralResult

RECEIPT_FIELDS = frozenset(
    {"write_status", "status", "code", "id", "fact_id", "proposal_id", "kind", "revision", "affected_ids", "draw_id"}
)
USAGE_COUNTERS = frozenset({"model_steps", "model_streams_this_execution", "replayed_model_steps"})
TOKEN_FIELDS = frozenset({"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"})


def public_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in RECEIPT_FIELDS.intersection(value):
        child = value[key]
        if isinstance(child, str) and len(child) <= 200 or type(child) is int and 0 <= child < 2**63:
            result[key] = child
        elif (
            key == "affected_ids"
            and isinstance(child, list)
            and len(child) <= 1024
            and all(isinstance(item, str) and len(item) <= 200 for item in child)
        ):
            result[key] = list(child)
    return result


def public_usage(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        key: child
        for key, child in value.items()
        if key in USAGE_COUNTERS and type(child) is int and 0 <= child < 2**63
    }
    reported = value.get("reported_tokens", {})
    result["reported_tokens"] = {
        key: child
        for key, child in (reported.items() if isinstance(reported, dict) else ())
        if key in TOKEN_FIELDS and type(child) is int and 0 <= child < 2**63
    }
    result["usage_known"] = bool(result["reported_tokens"])
    if type(value.get("offline")) is bool:
        result["offline"] = value["offline"]
    return result


def public_question(asked: dict[str, Any] | None, message_id: str) -> dict[str, Any] | None:
    if asked is None:
        return None
    value = dict(asked)
    if "ask_id" not in value:
        required = {"question", "options", "allow_free_text", "why"}
        if not required <= value.keys() or set(value) - required - {"slot", "changes_conclusion"}:
            raise EvidenceError("澄清提问结构无效")
        options = value["options"]
        if not isinstance(options, list) or any(not isinstance(item, str) for item in options):
            raise EvidenceError("澄清选项结构无效")
        ask_id = "ask-" + hashlib.sha256(message_id.encode()).hexdigest()[:24]
        value = {key: value[key] for key in required}
        value.update(ask_id=ask_id, multi=False)
        value["options"] = [{"id": f"{ask_id}-{index + 1}", "label": item} for index, item in enumerate(options)]
    try:
        return Asked.model_validate(value).model_dump()
    except (ValidationError, TypeError, ValueError):
        raise EvidenceError("澄清提问结构无效") from None


def build_envelope(
    run: Mapping[str, Any],
    checked: StructuralResult,
    *,
    message_id: str,
    receipts: tuple[dict[str, Any], ...] = (),
    asked: dict[str, Any] | None = None,
    usage: Mapping[str, Any] | None = None,
    review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    # Review has its own trusted service. Until connected it is explicitly skipped.
    if review is not None and review != {"state": "skipped", "reasons": []}:
        raise EvidenceError("评审结果尚未通过受信服务校验")
    result = {
        "schema": "core4.0",
        "schema_version": "core4.0",
        "message_id": message_id,
        "text": checked.text,
        "answer": checked.text,
        "receipts": [public_receipt(item) for item in receipts],
        "used_fact_ids": list(checked.used_fact_ids),
        "used_claim_ids": list(checked.used_claim_ids),
        "asked": public_question(asked, message_id),
        "options": None,
        "review": dict(review or {"state": "skipped", "reasons": []}),
        "usage": public_usage(usage or {}),
        "validation": {"status": "validated", "valid": True, "schema": "core4.0"},
        "meta": {
            "core_run": {"run_id": run["id"], "operation_id": run["operation_id"]},
            "subject_id": run["subject"],
            "case_ids": list(run["request"].get("case_ids", [])),
            "structural_warnings": list(checked.warnings),
        },
    }
    ensure_finite_json(result)
    try:
        return EnvelopeV1.model_validate(result).model_dump(by_alias=True, exclude_unset=True)
    except (ValidationError, TypeError, ValueError):
        raise EvidenceError("公开信封结构无效") from None


def validated_result(result: Any) -> bool:
    if not isinstance(result, dict) or not isinstance(result.get("validation"), dict):
        return False
    if result["validation"].get("status") != "validated":
        return False
    if result.get("schema_version") == "core3.0":
        return isinstance(result.get("answer"), str) and bool(result["answer"].strip())
    return (
        result.get("schema_version") == result.get("schema") == "core4.0"
        and isinstance(result.get("text"), str)
        and bool(result["text"].strip())
        and result.get("answer") == result["text"]
    )

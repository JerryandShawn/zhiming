"""Validate documentation examples only; no route implementation is implied."""

import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
import pytest

DOCUMENT = (
    Path(__file__).resolve().parents[3]
    / "docs/v4/contracts/api_modules_common_draft.md"
)
SCHEMA = json.loads(
    re.findall(r"```json\n(.*?)\n```", DOCUMENT.read_text(encoding="utf-8"), re.S)[0]
)


def validator(name):
    document = dict(SCHEMA, **{"$ref": f"#/$defs/{name}"})
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document)


@pytest.mark.parametrize(
    "body",
    [
        {"request_id": "synthetic:create:1", "expected_revision": 0},
        {"request_id": "synthetic-edit-1", "expected_revision": 9},
    ],
)
def test_explicit_write_identity_accepts_creation_and_observed_revision(body):
    validator("WriteIdentity").validate(body)


@pytest.mark.parametrize(
    "body",
    [
        {"request_id": "synthetic"},
        {"expected_revision": 1},
        {"request_id": "synthetic", "expected_revision": True},
        {"request_id": "synthetic", "expected_revision": -1},
        {"request_id": "synthetic", "expected_revision": "1"},
        {"request_id": "", "expected_revision": 1},
        {"request_id": "synthetic", "expected_revision": 1, "owner": "foreign"},
        {"request_id": "synthetic", "expected_revision": 1, "runtime": "v4"},
    ],
)
def test_missing_revision_coercion_and_trusted_identity_injection_are_rejected(body):
    assert not validator("WriteIdentity").is_valid(body)


@pytest.mark.parametrize(
    "status",
    [
        "saved",
        "updated",
        "deleted",
        "undone",
        "skipped",
        "pending_confirmation",
        "queued",
    ],
)
def test_receipt_status_is_explicit_even_when_http_request_is_accepted(status):
    result = {
        "ok": True,
        "request_id": "synthetic",
        "receipt": {
            "operation_id": "synthetic:op",
            "write_status": status,
            "entity_id": "synthetic:entity",
            "revision": 1,
        },
    }
    validator("WriteResult").validate(result)


@pytest.mark.parametrize(
    "receipt",
    [
        {"operation_id": "synthetic", "entity_id": "synthetic", "revision": 1},
        {
            "operation_id": "synthetic",
            "entity_id": "synthetic",
            "revision": 1,
            "write_status": "success_inferred",
        },
        {
            "operation_id": "synthetic",
            "entity_id": "synthetic",
            "revision": True,
            "write_status": "saved",
        },
    ],
)
def test_ui_cannot_invent_success_or_boolean_revision(receipt):
    assert not validator("WriteResult").is_valid(
        {"ok": True, "request_id": "synthetic", "receipt": receipt}
    )


def test_revision_conflict_error_has_safe_code_and_current_revision():
    result = {
        "ok": False,
        "request_id": "synthetic",
        "error": {
            "code": "REVISION_CONFLICT",
            "message": "内容已在别处更新，刷新后核对",
            "retryable": False,
            "current_revision": 2,
        },
    }
    validator("Error").validate(result)
    assert not validator("Error").is_valid(dict(result, stack="private"))


def test_error_payload_cannot_carry_private_original_or_fake_success():
    error = {"code": "SOURCE_REVOKED", "message": "来源已撤销", "retryable": False}
    assert not validator("Error").is_valid({"ok": True, "error": error})
    assert not validator("Error").is_valid(
        {"ok": False, "error": dict(error, source_text="private")}
    )


def test_source_references_are_versioned_but_do_not_claim_to_prove_source_authority():
    validator("SourceRef").validate(
        {"message_id": "synthetic:m1", "revision": 1, "start": 0, "end": 2}
    )
    assert not validator("SourceRef").is_valid(
        {"message_id": "synthetic:m1", "start": 0, "end": 2}
    )
    text = DOCUMENT.read_text(encoding="utf-8")
    assert "start<end" in text
    assert "JSON Schema无法独自验证原话或PG当前状态" in text

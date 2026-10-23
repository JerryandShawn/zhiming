"""Compatibility aliases cannot change the frozen result or fabricate saves."""

from __future__ import annotations

import copy

import pytest

from mingjing_core.adapters.legacy_web_result import (
    PENDING_MEMORY_NOTICE,
    legacy_web_history,
    legacy_web_result,
)
from mingjing_core.agent.envelope import build_envelope
from mingjing_core.agent.event_contracts import EnvelopeV1
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.validation.structural import check_structure


def envelope(receipts: tuple[dict, ...] = ()) -> dict:
    return build_envelope(
        {
            "id": "run-synthetic",
            "operation_id": "request-synthetic",
            "subject": "self",
            "request": {},
        },
        check_structure("合成回答", {}),
        message_id="message-synthetic",
        receipts=receipts,
    )


def test_core4_alias_keeps_all_frozen_fields_and_only_memory_effects() -> None:
    result = envelope(
        (
            {
                "kind": "fact",
                "id": "fact-synthetic",
                "write_status": "saved",
                "revision": 1,
            },
            {
                "kind": "note",
                "id": "note-synthetic",
                "write_status": "saved",
                "revision": 1,
            },
            {
                "kind": "case",
                "id": "case-synthetic",
                "write_status": "saved",
                "revision": 1,
            },
            {"kind": "fact", "fact_id": "deleted-synthetic", "write_status": "deleted"},
        )
    )
    before = copy.deepcopy(result)
    projected = legacy_web_result(result)
    assert projected.pop("memory_receipts") == [result["receipts"][index] for index in (0, 1, 3)]
    assert projected == before == result
    EnvelopeV1.model_validate(result)


def test_pending_stays_pending_and_has_no_saved_badge_input() -> None:
    receipt = {
        "kind": "proposal",
        "id": "proposal-synthetic",
        "write_status": "pending_confirmation",
        "revision": 1,
        "code": "sensitive_confirmation",
    }
    result = envelope((receipt,))
    projected = legacy_web_result(result)
    assert projected["memory_receipts"] == [receipt]
    assert projected["caveats"] == [PENDING_MEMORY_NOTICE]
    assert all(item["write_status"] != "saved" for item in projected["memory_receipts"])
    assert {key: projected[key] for key in result} == result
    projected["memory_receipts"][0]["write_status"] = "saved"
    assert projected["receipts"][0]["write_status"] == result["receipts"][0]["write_status"] == "pending_confirmation"
    assert "memory_receipts" not in result and "caveats" not in result


def test_legacy_core3_receipts_and_caveats_remain_unchanged() -> None:
    result = {
        "schema_version": "core3.0",
        "answer": "旧回答",
        "validation": {"status": "validated"},
        "memory_receipts": [{"write_status": "saved", "id": "legacy-fact"}],
        "caveats": ["旧边界"],
    }
    assert legacy_web_result(result) == dict(result, text=result["answer"])


def test_history_projection_is_only_for_validated_core4_assistant_metadata() -> None:
    value = envelope()
    assistant = {"role": "assistant", "content": value["text"], "meta": value}
    user = {"role": "user", "content": "合成原话", "meta": {"error": None}}
    legacy = {"role": "assistant", "content": "无旧信封", "meta": None}
    rows = [user, assistant, legacy]
    projected = legacy_web_history(rows)
    assert projected[0] is user and projected[2] is legacy
    assert projected[1]["meta"].pop("memory_receipts") == []
    assert projected[1] == assistant and "memory_receipts" not in value
    with pytest.raises(EvidenceError):
        legacy_web_result(dict(value, text="被修改的回答"))

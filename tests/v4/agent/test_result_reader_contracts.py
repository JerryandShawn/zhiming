"""Both public generations render without accepting model-authored validity."""

from __future__ import annotations

import copy

import pytest

from mingjing_core.adapters.channels.hermes import render_channel, validated_payload
from mingjing_core.agent.envelope import build_envelope
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.validation.structural import check_structure


def legacy_result() -> dict:
    return {
        "schema_version": "core3.0",
        "plain_summary": "合成旧回答",
        "answer": "合成旧回答",
        "actions": [],
        "decision_options": [],
        "cited_fact_ids": [],
        "cited_claim_ids": [],
        "validation": {"status": "validated", "valid": True, "schema": "core3.0"},
        "meta": {"core_run": {"run_id": "run-old", "dependencies": {"subject:self": 1}}},
    }


def modern_result() -> dict:
    return build_envelope(
        {"id": "run-new", "operation_id": "op-new", "subject": "self", "request": {}},
        check_structure("合成新回答", {}),
        message_id="message-new",
    )


@pytest.mark.parametrize("factory", [legacy_result, modern_result])
def test_rendering_keeps_exact_body_original_and_archived_hash(factory) -> None:
    result = factory()
    before, digest = copy.deepcopy(result), fingerprint(result)
    assert render_channel(result) == result["answer"]
    assert validated_payload(result) == before
    assert result == before and fingerprint(result) == digest
    assert "text" not in result if factory is legacy_result else result["text"] == result["answer"]


@pytest.mark.parametrize("change", ["private", "answer", "validation", "run", "meta_null", "schema"])
def test_core4_does_not_accept_private_keys_or_forged_public_fields(change: str) -> None:
    result = modern_result()
    if change == "private":
        result["reasoning"] = "PRIVATE_SENTINEL"
    elif change == "answer":
        result["answer"] = "其他正文"
    elif change == "validation":
        result["validation"]["valid"] = False
    elif change == "run":
        result["meta"]["core_run"].pop("run_id")
    elif change == "meta_null":
        result["meta"] = None
    else:
        result["schema"] = "core3.0"
    with pytest.raises(EvidenceError) as raised:
        render_channel(result)
    assert "PRIVATE_SENTINEL" not in str(raised.value)


@pytest.mark.parametrize("change", ["valid", "schema", "dependencies", "answer", "final_contract"])
def test_core3_still_requires_the_original_channel_contract(change: str) -> None:
    result = legacy_result()
    if change == "valid":
        result["validation"]["valid"] = False
    elif change == "schema":
        result["validation"]["schema"] = "core4.0"
    elif change == "dependencies":
        result["meta"]["core_run"]["dependencies"] = {}
    elif change == "answer":
        result["answer"] = " "
    else:
        result.pop("actions")
    with pytest.raises(EvidenceError):
        render_channel(result)

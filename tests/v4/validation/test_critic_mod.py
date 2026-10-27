"""Strict parser and isolated request projection, with no provider or transport."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import get_args

import pytest

from mingjing_core.domain.contracts import SaveReceipt
from mingjing_core.validation.critic import (
    CriticParseError,
    parse_attempts,
    parse_critic_output,
)
from mingjing_core.validation.critic_contracts import ITEM_TYPES, ProgramIssue
from mingjing_core.validation.critic_request import (
    RECEIPT_STATUSES,
    CriticMaterials,
    EvidenceSummary,
    ReceiptSummary,
    build_critic_request,
)

DRAFT = "这件事注定成功。明天是10月22日。"
PROMPT = "<!-- prompt: critic v2.1.0 -->\n独立的评审角色提示。"


def issue(item: str = "E1", **changes: object) -> dict[str, object]:
    result: dict[str, object] = {
        "item": item,
        "type": ITEM_TYPES[item],
        "quote": "明天是10月22日。",
        "rule": "与已提供日期矛盾",
        "evidence": "now:1" if item.startswith("E") else "",
        "fix_hint": "只修正日期",
        "confidence": 3,
    }
    result.update(changes)
    return result


def parse(row: dict[str, object]) -> object:
    return parse_critic_output(
        json.dumps({"issues": [row]}, ensure_ascii=False),
        draft=DRAFT,
        evidence_ids={"now:1"},
    )


@pytest.mark.parametrize("item", ITEM_TYPES)
def test_all_fourteen_atomic_item_types_parse_without_model_severity_or_verdict(
    item: str,
) -> None:
    output = parse(issue(item))
    assert output.issues[0].item == item
    assert not hasattr(output.issues[0], "severity") and not hasattr(output, "verdict")


@pytest.mark.parametrize("confidence", [0, 4, -1, True, False, 2.0, "2", None])
def test_confidence_is_strict_integer_one_two_three(confidence: object) -> None:
    with pytest.raises(CriticParseError):
        parse(issue(confidence=confidence))


@pytest.mark.parametrize(
    "field", ["item", "type", "quote", "rule", "evidence", "fix_hint", "confidence"]
)
def test_every_v2_field_is_required(field: str) -> None:
    row = issue()
    del row[field]
    with pytest.raises(CriticParseError):
        parse(row)


@pytest.mark.parametrize(
    "changes",
    [
        {"item": "E7"},
        {"type": "made_up_type"},
        {"type": "false_receipt"},
        {"quote": "不是原文"},
        {"quote": " "},
        {"rule": " "},
        {"fix_hint": " "},
        {"evidence": ""},
        {"evidence": "now:99"},
        {"evidence": "now:1 任意伪造依据"},
        {"severity": 5},
        {"verdict": "revise"},
        {"triggered": True},
    ],
)
def test_unobservable_extra_and_mismatched_claims_are_rejected(
    changes: dict[str, object],
) -> None:
    row = issue()
    row.update(changes)
    with pytest.raises(CriticParseError):
        parse(row)


@pytest.mark.parametrize("extra", ["verdict", "severity", "reasoning", "tool_calls"])
def test_output_extra_fields_do_not_smuggle_model_decisions(extra: str) -> None:
    with pytest.raises(CriticParseError):
        parse_critic_output(
            json.dumps({"issues": [], extra: "forbidden"}),
            draft=DRAFT,
            evidence_ids=set(),
        )


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "null",
        "[]",
        '{"issues":{}}',
        '{"issues":[],"issues":[]}',
        '{"issues":[],"x":NaN}',
        '```json\n{"issues":[]}\n```',
    ],
)
def test_parser_requires_one_canonical_json_object(raw: str) -> None:
    with pytest.raises(CriticParseError):
        parse_critic_output(raw, draft=DRAFT, evidence_ids={"now:1"})


def test_duplicate_atomic_items_and_nested_duplicate_keys_are_rejected() -> None:
    with pytest.raises(CriticParseError):
        parse_critic_output(
            json.dumps({"issues": [issue(), issue()]}),
            draft=DRAFT,
            evidence_ids={"now:1"},
        )
    with pytest.raises(CriticParseError, match="duplicate_json_key"):
        parse_critic_output(
            '{"issues":[{"confidence":2,"confidence":3}]}',
            draft=DRAFT,
            evidence_ids=set(),
        )


def test_two_already_obtained_attempts_fail_open_without_initiating_retry() -> None:
    first = parse_attempts(
        ["PRIVATE_SYNTHETIC_INVALID", '{"issues":[]}'], draft=DRAFT, evidence_ids=set()
    )
    assert first.attempts == 2 and not first.parse_failed
    failed = parse_attempts(
        ["PRIVATE_SYNTHETIC_INVALID", "bad"], draft=DRAFT, evidence_ids=set()
    )
    assert failed.attempts == 2 and failed.parse_failed and failed.output.issues == ()
    assert "PRIVATE_SYNTHETIC_INVALID" not in repr(failed)
    assert parse_attempts([], draft=DRAFT, evidence_ids=set()).error_codes == (
        "critic_unavailable",
    )
    with pytest.raises(ValueError, match="at most two"):
        parse_attempts(["bad", "bad", "bad"], draft=DRAFT, evidence_ids=set())


def test_parser_errors_and_repr_never_echo_private_text() -> None:
    secret = "PRIVATE_SYNTHETIC_MARKER"
    with pytest.raises(CriticParseError) as error:
        parse_critic_output(
            json.dumps({"issues": [{"quote": secret}]}),
            draft=secret,
            evidence_ids=set(),
        )
    assert secret not in str(error.value)
    with pytest.raises(CriticParseError, match="invalid_output_size"):
        parse_critic_output("x" * 262_145, draft="x", evidence_ids=set())


def test_isolated_request_is_an_explicit_projection_with_fixed_high_effort() -> None:
    unrelated_run = {
        "system": "MAIN_SYSTEM_PRIVATE",
        "reasoning": "MAIN_REASONING_PRIVATE",
        "tool_trace": "RAW_TRACE_PRIVATE",
        "history": "OLD_MESSAGES_PRIVATE",
    }
    materials = CriticMaterials(
        "本轮合成问题",
        "2026-10-21 周三",
        DRAFT,
        memory_summaries=(EvidenceSummary("memory:m1", "经授权的单句记忆摘要"),),
        chart_summaries=(EvidenceSummary("claim:c1", "经过程序声明的盘面摘要"),),
        profile_summaries=(EvidenceSummary("profile:p1", "当前版本摘要"),),
        receipts=(ReceiptSummary("receipt:r1", "saved", "本轮实际写入结果"),),
    )
    request = build_critic_request(
        materials, critic_prompt=PROMPT, primary_model="synthetic-primary"
    ).as_dict()
    encoded = json.dumps(request, ensure_ascii=False)
    assert all(value not in encoded for value in unrelated_run.values())
    assert (
        request["role"],
        request["model"],
        request["effort"],
        request["new_session"],
    ) == (
        "critic",
        "synthetic-primary",
        "high",
        True,
    )
    assert len(request["messages"]) == 2
    payload = json.loads(request["messages"][1]["content"])
    assert set(payload) == {
        "user_message",
        "now_block",
        "draft",
        "memory_summaries",
        "chart_summaries",
        "profile_summaries",
        "receipts",
        "program_issues",
        "evidence_reference_ids",
    }
    assert {
        "now:1",
        "memory:m1",
        "receipt:r1",
        "user:current",
        "receipts",
    } <= materials.evidence_ids
    assert "本轮合成问题" not in repr(materials)
    with pytest.raises(TypeError):
        CriticMaterials("u", "n", "d", **unrelated_run)


def test_request_projection_copies_mutable_lists_and_returns_fresh_payloads() -> None:
    refs = [EvidenceSummary("m1", "PRIVATE_SUMMARY")]
    materials = CriticMaterials("u", "now", "draft", memory_summaries=refs)
    refs.clear()
    payload = materials.payload()
    payload["memory_summaries"].clear()
    assert (
        len(materials.memory_summaries)
        == len(materials.payload()["memory_summaries"])
        == 1
    )
    request = build_critic_request(
        materials, critic_prompt=PROMPT, primary_model="synthetic-primary"
    )
    assert "PRIVATE_SUMMARY" not in repr(request)
    with pytest.raises(FrozenInstanceError):
        request.prompt = "changed"


@pytest.mark.parametrize("value", ["now", "now:1", "user:current", "receipts"])
def test_materials_cannot_replace_reserved_evidence_references(value: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        CriticMaterials(
            "u",
            "one line",
            "draft",
            memory_summaries=(EvidenceSummary(value, "summary"),),
        )


def test_materials_reject_raw_records_duplicate_ids_wrong_prompt_and_wrong_receipt_status() -> (
    None
):
    with pytest.raises(ValueError, match="typed summaries"):
        CriticMaterials(
            "u", "n", "d", memory_summaries=({"id": "m", "summary": "raw record"},)
        )
    with pytest.raises(ValueError, match="unique"):
        CriticMaterials(
            "u",
            "n",
            "d",
            chart_summaries=(EvidenceSummary("x", "one"), EvidenceSummary("x", "two")),
        )
    with pytest.raises(ValueError, match="independent"):
        build_critic_request(
            CriticMaterials("u", "n", "d"),
            critic_prompt="main system prompt",
            primary_model="synthetic-primary",
        )
    with pytest.raises(ValueError, match="receipt status"):
        ReceiptSummary("r", "model_claimed_saved", "not a program receipt")


def test_program_issues_are_typed_evidence_findings_without_a_model_severity() -> None:
    finding = ProgramIssue(
        "E1", "明天是10月22日。", "date mismatch", "now:1", "修正日期"
    )
    material = CriticMaterials("u", "now", DRAFT, program_issues=(finding,))
    assert material.payload()["program_issues"][0]["item"] == "E1"
    assert not hasattr(finding, "severity")
    with pytest.raises(ValueError, match="E1-E5"):
        ProgramIssue("J1", "quote", "rule", "ref", "fix")


@pytest.mark.parametrize(
    "raw",
    ["\ud800", '{"issues":[],"huge":' + "9" * 5000 + "}", "[" * 2000 + "]" * 2000],
)
def test_untrusted_unicode_integer_and_depth_limits_still_fail_open(raw: str) -> None:
    parsed = parse_attempts([raw, "bad"], draft="original", evidence_ids=set())
    assert parsed.parse_failed and parsed.output.issues == () and parsed.attempts == 2
    assert all(len(code) < 50 for code in parsed.error_codes)


@pytest.mark.parametrize("status", sorted(RECEIPT_STATUSES))
def test_every_real_and_legacy_receipt_status_is_projected_without_becoming_saved(
    status: str,
) -> None:
    receipt = ReceiptSummary("receipt:r", status, "本轮实际写入结果摘要")
    request = build_critic_request(
        CriticMaterials("u", "now", "已保存。", receipts=(receipt,)),
        critic_prompt=PROMPT,
        primary_model="synthetic-primary",
    )
    payload = json.loads(request.payload_json)
    assert payload["receipts"] == [
        {"id": "receipt:r", "status": status, "summary": "本轮实际写入结果摘要"}
    ]
    if status not in {"saved", "updated"}:
        assert payload["receipts"][0]["status"] not in {"saved", "updated"}
    assert "receipt:r" in payload["evidence_reference_ids"]


def test_receipt_projection_covers_the_current_domain_contract_without_raw_metadata() -> (
    None
):
    actual_statuses = set(get_args(SaveReceipt.model_fields["write_status"].annotation))
    assert actual_statuses <= RECEIPT_STATUSES
    for field in ("content", "source_text", "raw_payload", "owner_id", "reasoning"):
        with pytest.raises(TypeError):
            ReceiptSummary(
                "r",
                "pending_confirmation",
                "safe summary",
                **{field: "PRIVATE_SYNTHETIC_MARKER"},
            )
    with pytest.raises(ValueError, match="typed summaries"):
        CriticMaterials(
            "u",
            "n",
            "d",
            receipts=(
                {"write_status": "pending_confirmation", "source_text": "private"},
            ),
        )


@pytest.mark.parametrize("model", ["k3.1-pro", "k3-256k", "synthetic-future-model"])
def test_critic_request_follows_the_explicit_primary_configuration(model: str) -> None:
    request = build_critic_request(
        CriticMaterials("u", "n", "d"), critic_prompt=PROMPT, primary_model=model
    )
    assert request.as_dict()["model"] == model
    assert request.as_dict()["new_session"] is True


@pytest.mark.parametrize("model", ["", " ", None, 123])
def test_missing_primary_configuration_is_not_replaced_with_a_fixed_fallback(
    model: object,
) -> None:
    with pytest.raises(ValueError, match="primary model"):
        build_critic_request(
            CriticMaterials("u", "n", "d"), critic_prompt=PROMPT, primary_model=model
        )


def test_removed_e6_cannot_enter_the_fourteen_item_protocol() -> None:
    assert len(ITEM_TYPES) == 14 and "E6" not in ITEM_TYPES
    with pytest.raises(CriticParseError):
        parse(dict(issue(), item="E6", type="crisis_missed"))
    with pytest.raises(ValueError, match="E1-E5"):
        ProgramIssue("E6", "q", "r", "now", "f")

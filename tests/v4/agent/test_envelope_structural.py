"""Pure shape checks do not substitute for the PG commit-gate tests."""

from __future__ import annotations

from typing import Any

import pytest

from mingjing_core.agent.envelope import build_envelope, public_receipt, public_usage, validated_result
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.validation.structural import ANNOTATION, check_structure

ALIASES = {
    "f1": {"kind": "fact", "id": "fact-synthetic", "revision": 1},
    "c1": {"kind": "interpretive_claim", "id": "claim-synthetic", "revision": 2},
    "m1": {"kind": "message", "id": "message-synthetic", "revision": 1},
}
RUN = {"id": "run-synthetic", "operation_id": "request-synthetic", "subject": "self", "request": {}}


def test_run_local_aliases_resolve_once_and_unknown_is_removed_without_body_logs() -> None:
    result = check_structure("依据〔f1〕〔m1〕〔c1〕〔f1〕，未知〔f999〕", ALIASES)
    assert result.used_fact_ids == ("fact-synthetic",) and result.used_claim_ids == ("claim-synthetic",)
    assert "f999" not in result.text and len(result.cited_keys) == 3
    assert result.warnings == ({"code": "unknown_alias_removed", "count": 1},)


@pytest.mark.parametrize("text", ["我记下了", "我已记下了", "我已经记下了", "已记住", "已经记住", "已保存", "已经保存"])
def test_unsupported_save_status_is_qualified(text: str) -> None:
    assert ANNOTATION in check_structure(text, {}).text


@pytest.mark.parametrize(
    "text", ["还没已保存", "尚未已记住", "没有已保存", "未已保存", "没已保存", "还没有保存", "无需保存"]
)
def test_absent_status_claim_does_not_get_an_annotation(text: str) -> None:
    assert ANNOTATION not in check_structure(text, {}).text


@pytest.mark.parametrize(
    "status,kind,qualified",
    [
        ("saved", "fact", False),
        ("saved", "note", False),
        ("saved", "thread", True),
        ("pending_confirmation", "fact", True),
        ("stopped", "fact", True),
        ("deleted", "fact", True),
    ],
)
def test_only_real_persistence_receipts_support_save_language(status: str, kind: str, qualified: bool) -> None:
    result = check_structure("我记下了", {}, ({"write_status": status, "kind": kind},))
    assert (ANNOTATION in result.text) is qualified


@pytest.mark.parametrize("revision", [True, 0, -1, "1", None])
def test_alias_revision_is_strict(revision: Any) -> None:
    with pytest.raises(EvidenceError):
        check_structure("〔f1〕", {"f1": dict(ALIASES["f1"], revision=revision)})


def test_empty_text_has_nonempty_fallback_and_deleted_marker_is_preserved() -> None:
    assert check_structure(" ", {}).text.strip()
    assert check_structure("〔已删除的内容〕", {}).text == "〔已删除的内容〕"


def test_envelope_projects_only_public_receipt_and_usage_fields() -> None:
    receipt = {"kind": "fact", "id": "fact-synthetic", "write_status": "saved", "reasoning": "private"}
    usage = {
        "reported_tokens": {"input_tokens": 15, "output_tokens": True, "reasoning": "private"},
        "reasoning": "private",
        "model_steps": 1,
        "offline": True,
    }
    result = build_envelope(
        RUN,
        check_structure("合成回答〔f1〕", ALIASES),
        message_id="message-synthetic",
        receipts=(receipt,),
        usage=usage,
    )
    assert validated_result(result) and result["answer"] == result["text"]
    assert result["receipts"] == [{"kind": "fact", "id": "fact-synthetic", "write_status": "saved"}]
    assert result["usage"]["reported_tokens"] == {"input_tokens": 15}
    assert "private" not in str(result) and result["review"] == {"state": "skipped", "reasons": []}


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"validation": None},
        {"validation": []},
        {"schema_version": "core4.0", "validation": {"status": "validated"}},
    ],
)
def test_invalid_envelope_shape_fails_closed(value: Any) -> None:
    assert not validated_result(value)


def test_core3_remains_accepted_and_cannot_inject_a_review_result() -> None:
    assert validated_result(
        {"schema_version": "core3.0", "answer": "旧合成回答", "validation": {"status": "validated"}}
    )
    with pytest.raises(EvidenceError):
        build_envelope(RUN, check_structure("合成", {}), message_id="m", review={"status": "passed"})
    assert public_usage({"model_steps": True})["reported_tokens"] == {}
    assert public_receipt({"id": {"private": "body"}, "reasoning": "body"}) == {}

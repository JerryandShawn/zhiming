"""Behavioral acceptance of new opt-in builders, including raw literal and wire-byte attacks."""

import copy
import json
import random
from datetime import date

import pytest

from mingjing_core.adapters.channels.card_limits_official_v3 import (
    MAX_WIRE_BYTES,
    SAFE_CARD_BYTES,
)
from mingjing_core.adapters.channels.cards_contracts import (
    BriefSection,
    CardAction,
    ReceiptLine,
    RouteLabel,
)
from mingjing_core.adapters.channels.cards_official_v3 import (
    answer_card,
    brief_card,
    card_sizes,
    followup_card,
    literal,
    memory_receipt_card,
    proposal_card,
    question_card,
    route_card,
    validate_card,
)


def token(index: int) -> str:
    return f"offline_token_{index:020d}"


def documents() -> list[dict]:
    return [
        answer_card("已核验的回答。"),
        answer_card("", streaming=True),
        question_card(
            "你怎么想？", why="补足信息", options=[CardAction("先看看", token(1))]
        ),
        memory_receipt_card([ReceiptLine("r1", "saved", "已确认事实", token(2))]),
        proposal_card(
            "候选私人事实",
            remember_token=token(3),
            decline_token=token(4),
            always_token=token(5),
        ),
        followup_card("今天还好吗？", sensitive=True),
        brief_card(
            date(2026, 10, 21),
            calendar="周三",
            plans="没有已确认安排",
            daily_flow="平稳",
            closing="慢慢来。",
        ),
        route_card(RouteLabel("日常", "近况", token(6), token(7))),
    ]


@pytest.mark.parametrize("document", documents())
def test_all_kinds_are_isolated_budgeted_update_multi(document: dict) -> None:
    validated = validate_card(document)
    assert validated == document and validated is not document
    assert validated["config"]["update_multi"] is True
    assert validated["body"]["elements"]
    inner, wire = card_sizes(validated)
    assert inner <= SAFE_CARD_BYTES and wire <= MAX_WIRE_BYTES
    validated["body"]["elements"].clear()
    assert document["body"]["elements"]


@pytest.mark.parametrize(
    "raw,escaped",
    [
        (">", "&#62;"),
        ("<", "&#60;"),
        ("*", "&#42;"),
        ("_", "&#95;"),
        ("~", "&sim;"),
        ("`", "&#96;"),
        ("[", "&#91;"),
        ("]", "&#93;"),
        ("(", "&#40;"),
        (")", "&#41;"),
        ("#", "&#35;"),
        ("!", "&#33;"),
        ("\\", "&#92;"),
        ("&", "&#38;"),
        ("|", "&#124;"),
        ("-a", "&#45;a"),
        ("a-b", "a&#45;b"),
        ("a\n-b", "a\n&#45;b"),
        ("&#60;", "&#38;&#35;60;"),
    ],
)
def test_escape_original_characters_once(raw: str, escaped: str) -> None:
    assert literal(raw) == escaped


def test_typed_literal_fields_cannot_inject_mention_link_or_list() -> None:
    raw = "<at id=all>*大事*</at>\n- [链接](https://example.invalid)\\path"
    card = question_card(raw, why=raw, options=[])
    content = card["body"]["elements"][0]["content"]
    assert raw not in content and "<at" not in content and "\\path" not in content
    assert literal(raw) in content
    assert (
        "**" in content
    )  # Only the builder's intentional template is Markdown syntax.


@pytest.mark.parametrize(
    "sample",
    ["长" * 20_000, '"' * 20_000, "\\" * 20_000, "😀" * 20_000],
    ids=["cjk", "quotes", "backslashes", "emoji"],
)
def test_large_answer_keeps_real_receipt_and_route_actions(sample: str) -> None:
    receipt = ReceiptLine("write1", "updated", "已确认的改动", token(1))
    card = answer_card(
        sample,
        evidence=sample,
        receipts=[receipt],
        route=RouteLabel("工作", "面试", token(2), token(3)),
        open_url="https://example.invalid/app",
    )
    rows = card["body"]["elements"]
    assert any(
        row.get("element_id") == "receipt_0" and "改好了" in row["content"]
        for row in rows
    )
    assert sum(row["tag"] == "button" for row in rows) == 4
    assert any(
        row.get("element_id") == "answer" and "内容已缩略" in row["content"]
        for row in rows
    )
    assert all(row.get("element_id") != "answer_full" for row in rows)
    assert card_sizes(card)[1] <= MAX_WIRE_BYTES


def test_large_brief_is_budgeted_without_duplicate_full_body() -> None:
    card = brief_card(
        date(2026, 10, 21),
        calendar="历" * 4000,
        plans="事" * 4000,
        daily_flow="流" * 4000,
        closing="结束",
        sections=tuple(BriefSection(f"区{i}", ("😀" * 2000,) * 30) for i in range(7)),
        open_url="https://example.invalid/app",
    )
    assert (
        card_sizes(card)[0] <= SAFE_CARD_BYTES and card_sizes(card)[1] <= MAX_WIRE_BYTES
    )
    assert len(card["body"]["elements"]) == 12
    assert "内容已缩略" in json.dumps(card, ensure_ascii=False)
    assert card["body"]["elements"][-1]["behaviors"][0]["type"] == "open_url"


def test_mandatory_oversized_receipts_reject_instead_of_disappearing() -> None:
    receipts = [ReceiptLine(f"r{i}", "saved", "😀" * 500) for i in range(50)]
    with pytest.raises(ValueError, match="card_byte_budget_exceeded"):
        memory_receipt_card(receipts)


@pytest.mark.parametrize(
    "content", ['"' * 15_000, "\\" * 15_000], ids=["quotes", "backslashes"]
)
def test_complete_nested_wire_budget_independent_of_inner_budget(content: str) -> None:
    card = answer_card("x")
    card["body"]["elements"][0]["content"] = content
    inner, wire = card_sizes(card)
    assert inner > SAFE_CARD_BYTES or wire > MAX_WIRE_BYTES
    with pytest.raises(ValueError, match="card_byte_budget_exceeded"):
        validate_card(card)


@pytest.mark.parametrize(
    "field,value", [("schema", "1.0"), ("config", None), ("body", []), ("header", {})]
)
def test_malformed_envelope_fails_controlled(field: str, value: object) -> None:
    card = answer_card("x")
    card[field] = value
    with pytest.raises(ValueError):
        validate_card(card)


@pytest.mark.parametrize(
    "change",
    ["update_multi", "streaming_mode", "summary", "empty", "ids", "surrogate", "nan"],
)
def test_invalid_mutations_fail_closed(change: str) -> None:
    card = answer_card("x")
    if change == "update_multi":
        card["config"]["update_multi"] = False
    elif change == "streaming_mode":
        card["config"]["streaming_mode"] = 1
    elif change == "summary":
        card["config"]["summary"]["content"] = ""
    elif change == "empty":
        card["body"]["elements"][0]["content"] = ""
    elif change == "ids":
        card["body"]["elements"] *= 2
    elif change == "surrogate":
        card["body"]["elements"][0]["content"] = "\ud800"
    else:
        card["extra"] = float("nan")
    with pytest.raises(ValueError):
        validate_card(card)


def test_cycle_and_bad_json_keys_fail_controlled_without_payload_in_error() -> None:
    card = answer_card("private")
    card["recursive"] = card
    with pytest.raises(ValueError, match="card_json_invalid") as caught:
        validate_card(card)
    assert "private" not in str(caught.value)
    with pytest.raises(ValueError, match="card_json_invalid"):
        validate_card({1: "private"})


@pytest.mark.parametrize("count", [199, 200, 201])
def test_body_component_limit_excludes_property_objects(count: int) -> None:
    card = answer_card("x")
    card["body"]["elements"] = [
        {"tag": "markdown", "element_id": f"line_{i}", "content": "x"}
        for i in range(count)
    ]
    if count <= 200:
        assert validate_card(card)["header"]["title"]["tag"] == "plain_text"
    else:
        with pytest.raises(ValueError, match="card_component_limit"):
            validate_card(card)


@pytest.mark.parametrize(
    "element_id", ["1start", "a" * 21, "a-b", "字", "a/b", "a\n", "", True]
)
def test_invalid_component_identity(element_id: object) -> None:
    card = answer_card("x")
    card["body"]["elements"][0]["element_id"] = element_id
    with pytest.raises(ValueError):
        validate_card(card)


def test_buttons_remain_bound_and_duplicate_actions_reject() -> None:
    with pytest.raises(ValueError, match="card_duplicate_identity"):
        proposal_card(
            "x", remember_token=token(1), decline_token=token(1), always_token=token(3)
        )
    with pytest.raises(ValueError, match="card_action_limit"):
        question_card(
            "x", why="y", options=[CardAction(str(i), token(i), True) for i in range(2)]
        )
    original = question_card("x", why="y", options=[CardAction("a", token(1))])
    mutated = copy.deepcopy(original)
    mutated["body"]["elements"][1]["behaviors"].append(
        {"type": "open_url", "default_url": "https://example.invalid"}
    )
    with pytest.raises(ValueError, match="card_button_behavior_invalid"):
        validate_card(mutated)
    assert original["body"]["elements"][1]["behaviors"][0]["value"]["t"] == token(1)


def test_thousand_random_unicode_documents_have_both_budgets_and_preserve_actions() -> (
    None
):
    generator = random.Random(20261021)
    alphabet = '汉😀abc"\\*[_<>&|\n'
    for index in range(1000):
        raw = "".join(generator.choices(alphabet, k=generator.randrange(1, 20_001)))
        card = answer_card(
            raw, receipts=[ReceiptLine("r", "saved", "原回执", token(index))]
        )
        assert (
            card_sizes(card)[0] <= SAFE_CARD_BYTES
            and card_sizes(card)[1] <= MAX_WIRE_BYTES
        )
        assert card["body"]["elements"][-1]["behaviors"][0]["value"]["t"] == token(
            index
        )


def test_stream_placeholder_never_uses_undocumented_empty_component() -> None:
    card = answer_card("", streaming=True)
    assert all(row["content"].strip() for row in card["body"]["elements"])
    assert card["config"]["streaming_mode"] is True
    with pytest.raises(ValueError, match="card_stream_placeholder_mixed"):
        answer_card("", streaming=True, receipts=[ReceiptLine("r", "saved", "x")])


def test_followup_sensitive_preview_has_no_private_content() -> None:
    card = followup_card("你的检查结果还好吗？", category="health", sensitive=True)
    assert "检查" not in card["config"]["summary"]["content"]
    assert "检查" in card["body"]["elements"][0]["content"]

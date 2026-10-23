"""Independent original-input/budget/receipt checks and document-26 handoff gaps."""

import json
from datetime import date
from pathlib import Path

import pytest

from mingjing_core.adapters.channels.cards_contracts import BriefSection, CardAction, ReceiptLine, RouteLabel
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

GOLDEN = json.loads((Path(__file__).with_name("fixtures") / "expected_contract_mod.json").read_text(encoding="utf-8"))
GUIDE_PATH = Path("docs/v4/integration/mod/P9_official_20261021.md")
ESCAPES = [case for case in GOLDEN["cases"] if case["id"].startswith(("ESCAPE_OFFICIAL_", "ESCAPE_PROJECT_"))]


def token(number: int) -> str:
    return f"synthetic_action_{number:032d}"


def markdown_text(card: dict) -> str:
    return "\n".join(item["content"] for item in card["body"]["elements"] if item["tag"] == "markdown")


def action_tokens(card: dict) -> list[str]:
    return [
        action["value"]["t"]
        for item in card["body"]["elements"]
        if item["tag"] == "button"
        for action in item["behaviors"]
        if action["type"] == "callback"
    ]


@pytest.mark.parametrize("case", ESCAPES, ids=lambda case: case["id"])
def test_literal_matches_preproduct_normative_matrix(case: dict) -> None:
    assert literal(case["given"]["text"]) == case["expected"]["literal_text"]


def test_interior_hyphen_uses_the_explicit_numeric_entity_policy() -> None:
    assert literal("a-b") == "a&#45;b"


@pytest.mark.parametrize("text", ["a" * 1601, "汉" * 8000], ids=["ascii1601", "han8000"])
def test_answer_that_fits_both_real_budgets_keeps_full_original(text: str) -> None:
    card = answer_card(text)
    assert text in markdown_text(card)
    inner, wire = card_sizes(card)
    assert inner <= 28000 and wire <= 30000
    assert "内容已缩略" not in markdown_text(card)


def test_evidence_that_fits_budget_is_not_prematurely_truncated() -> None:
    evidence = "synthetic-evidence-" * 90
    card = answer_card("合成回答", evidence=evidence)
    assert evidence in markdown_text(card)
    assert "内容已缩略" not in markdown_text(card)


def test_oversized_answer_preserves_receipt_status_tokens_and_route() -> None:
    receipt = ReceiptLine("receipt-one", "saved", "真实合成回执*", token(1))
    route = RouteLabel("成长*", "考试#", token(2), token(3))
    card = answer_card("大" * 10000, evidence="依" * 5000, receipts=(receipt,), route=route)
    assert "内容已缩略" in markdown_text(card)
    assert "记下了：真实合成回执&#42;" in markdown_text(card)
    assert "归入：成长&#42;·考试&#35;" in markdown_text(card)
    assert action_tokens(card) == [token(1), token(2), token(3)]
    assert card_sizes(card)[0] <= 28000 and card_sizes(card)[1] <= 30000


@pytest.mark.parametrize(
    ("status", "label"),
    [
        ("saved", "记下了"),
        ("updated", "改好了"),
        ("pending_confirmation", "待你确认"),
        ("stopped", "已停用"),
        ("deleted", "已删除"),
        ("rejected", "这次没有记下"),
        ("skipped", "这次没有记下"),
        ("failed", "这次没有记下"),
        ("undone", "已撤销"),
    ],
)
def test_receipt_states_are_never_promoted_to_success(status: str, label: str) -> None:
    card = memory_receipt_card((ReceiptLine("receipt-mod", status, "合成*原文"),))
    assert markdown_text(card) == f"{label}：合成&#42;原文"
    assert not action_tokens(card)


def test_mandatory_receipts_over_budget_reject_instead_of_disappearing() -> None:
    receipts = tuple(ReceiptLine(f"receipt-{i}", "saved", "汉" * 500) for i in range(30))
    with pytest.raises(ValueError):
        memory_receipt_card(receipts)


def test_question_literal_fields_and_selection_do_not_become_markdown() -> None:
    choices = (CardAction("*选项*", token(1), True), CardAction("普通", token(2)))
    card = question_card("[合成问题]", why="*原因*", options=choices)
    text = markdown_text(card)
    assert "&#91;合成问题&#93;" in text and "&#42;原因&#42;" in text
    assert action_tokens(card) == [token(1), token(2)]
    assert card["body"]["elements"][1]["text"] == {"tag": "plain_text", "content": "*选项*"}
    selected = question_card("[合成问题]", why="*原因*", options=choices, selected_label="*选项*")
    assert "你选了：&#42;选项&#42;" in markdown_text(selected)
    assert not action_tokens(selected)


def test_sensitive_proposal_keeps_three_distinct_actions_and_literal_summary() -> None:
    card = proposal_card("*私人* [内容]", remember_token=token(1), decline_token=token(2), always_token=token(3))
    assert "&#42;私人&#42; &#91;内容&#93;" in markdown_text(card)
    assert action_tokens(card) == [token(1), token(2), token(3)]
    assert sum(item.get("type") == "primary" for item in card["body"]["elements"]) == 1


def test_route_fields_escape_from_original_input_and_keep_actions() -> None:
    card = route_card(RouteLabel("工作*", "[目标]", token(1), token(2)))
    assert "归入：工作&#42;·&#91;目标&#93;" in markdown_text(card)
    assert action_tokens(card) == [token(1), token(2)]


def test_sensitive_followup_preview_is_safe_without_losing_reply_actions() -> None:
    card = followup_card(
        "合成健康检查结果到了。想聊聊吗？",
        replies=(CardAction("好", token(1)), CardAction("晚点", token(2))),
        category="health",
        sensitive=True,
    )
    assert "健康检查" not in card["config"]["summary"]["content"]
    assert action_tokens(card) == [token(1), token(2)]


def test_large_brief_shortens_body_but_preserves_day_area_headings_and_open_link() -> None:
    sections = tuple(BriefSection(f"合成区{i}", tuple("汉" * 800 for _ in range(20))) for i in range(7))
    card = brief_card(
        date(2026, 10, 21),
        calendar="合成历法",
        plans="合成安排",
        daily_flow="合成流日",
        closing="合成结语",
        sections=sections,
        open_url="https://example.invalid/mingjing",
    )
    assert "10月21日 周三" in card["header"]["title"]["content"]
    assert "内容已缩略" in markdown_text(card)
    assert all(f"合成区{i}" in markdown_text(card) for i in range(7))
    assert card["body"]["elements"][-1]["behaviors"][0]["default_url"] == "https://example.invalid/mingjing"
    assert card_sizes(card)[0] <= 28000 and card_sizes(card)[1] <= 30000


def test_utf8_nested_wire_expansion_is_measured_separately_from_inner_card() -> None:
    card = answer_card("合成回答")
    card["body"]["elements"][0]["content"] = "\\" * 10000
    inner = json.dumps(card, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    envelope = {"card": {"type": "card_json", "data": inner}, "uuid": "f" * 40, "sequence": 2147483647}
    wire = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    assert card_sizes(card) == (len(inner.encode("utf-8")), len(wire.encode("utf-8")))
    assert len(inner.encode("utf-8")) < 28000 < len(wire.encode("utf-8"))
    with pytest.raises(ValueError):
        validate_card(card)


@pytest.mark.parametrize("children", [199, 200])
def test_nested_component_limit_does_not_count_header_title_properties(children: int) -> None:
    card = answer_card("合成回答")
    card["body"]["elements"] = [
        {
            "tag": "collapsible_panel",
            "expanded": False,
            "header": {"title": {"tag": "plain_text", "content": "合成折叠"}},
            "elements": [{"tag": "markdown", "content": "合成"} for _ in range(children)],
        }
    ]
    if children == 199:
        assert validate_card(card)["body"]["elements"]
    else:
        with pytest.raises(ValueError):
            validate_card(card)


@pytest.mark.parametrize(
    "field",
    ["cardkit:card:write", "im:message:send_as_bot", "im:message:update", "header.event_id", "event.action.value.t"],
)
def test_guide_names_actual_permissions_and_callback_fields(field: str) -> None:
    assert field in GUIDE_PATH.read_text(encoding="utf-8")


def test_guide_official_rich_text_url_is_the_v2_source_from_26() -> None:
    expected = GOLDEN["official_reference_urls"]["rich_text"]
    assert expected in GUIDE_PATH.read_text(encoding="utf-8")

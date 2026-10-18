"""Independent offline card contracts; these tests do not establish Feishu wire compatibility."""

import json
from collections.abc import Iterator
from copy import deepcopy
from datetime import date
from typing import Any

import pytest

from mingjing_core.adapters.channels.card_elements import literal
from mingjing_core.adapters.channels.cards import (
    answer_card,
    brief_card,
    followup_card,
    memory_receipt_card,
    proposal_card,
    question_card,
    route_card,
)
from mingjing_core.adapters.channels.cards_contracts import BriefSection, CardAction, ReceiptLine, RouteLabel


def _token(number: int) -> str:
    return f"{number:032x}"


def _actions(count: int = 2) -> list[CardAction]:
    return [CardAction(f"选项{i}", _token(i + 1)) for i in range(count)]


def _route() -> RouteLabel:
    return RouteLabel("身心", "合成敏感话题", _token(10), _token(11))


def _walk(elements: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for element in elements:
        yield element
        yield from _walk(element.get("elements", []))


def _buttons(card: dict[str, Any]) -> list[dict[str, Any]]:
    return [element for element in _walk(card["body"]["elements"]) if element["tag"] == "button"]


def _content(card: dict[str, Any]) -> str:
    return "\n".join(element.get("content", "") for element in _walk(card["body"]["elements"]))


def _cards() -> list[dict[str, Any]]:
    return [
        answer_card("合成回答", route=_route()),
        question_card("合成问题", why="核实依据", options=_actions()),
        memory_receipt_card((ReceiptLine("receipt-1", "saved", "合成偏好", _token(20)),)),
        proposal_card("合成提案", remember_token=_token(30), decline_token=_token(31), always_token=_token(32)),
        followup_card("合成跟进。", replies=_actions(), category="health"),
        brief_card(
            date(2026, 10, 17), calendar="合成历法", plans="合成安排", daily_flow="合成流日", closing="合成结尾"
        ),
        route_card(_route()),
    ]


@pytest.mark.parametrize("index", range(7))
def test_all_seven_candidates_are_json_two_with_opaque_bounded_actions(index: int) -> None:
    result = _cards()[index]
    assert result["schema"] == "2.0" and json.loads(json.dumps(result, ensure_ascii=False)) == result
    assert result["header"]["template"] == "carmine"
    assert len(_buttons(result)) <= 4
    for button in _buttons(result):
        for behavior in button["behaviors"]:
            if behavior["type"] == "callback":
                assert set(behavior["value"]) == {"t"}
                assert len(behavior["value"]["t"]) >= 32
    assert "https://" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize("bad", ["short", "a" * 31, "a" * 129, "合成" * 32, "<script>x</script>", '{"owner":"x"}'])
def test_callback_token_never_contains_embedded_identity_or_markup(bad: str) -> None:
    with pytest.raises(ValueError) as error:
        CardAction("合成按钮", bad)
    assert bad not in str(error.value)


def test_one_token_cannot_authorize_multiple_visible_operations() -> None:
    with pytest.raises(ValueError, match="凭证"):
        question_card("问题", why="依据", options=[CardAction("甲", _token(1)), CardAction("乙", _token(1))])
    with pytest.raises(ValueError, match="凭证"):
        proposal_card("摘要", remember_token=_token(1), decline_token=_token(1), always_token=_token(1))
    with pytest.raises(ValueError, match="独立"):
        RouteLabel("日常", "话题", _token(1), _token(1))


def test_cardwide_button_budget_counts_receipts_route_and_link_together() -> None:
    receipts = (
        ReceiptLine("receipt-1", "saved", "偏好一", _token(20)),
        ReceiptLine("receipt-2", "updated", "偏好二", _token(21)),
    )
    result = answer_card("回答", receipts=receipts, route=_route())
    assert len(_buttons(result)) == 4
    with pytest.raises(ValueError, match="四个"):
        answer_card("回答", receipts=receipts, route=_route(), open_url="https://app.example.invalid/#/me")


def test_question_with_zero_choices_still_allows_free_text() -> None:
    result = question_card("你最在乎什么？", why="不同取舍会改变建议", options=())
    assert not _buttons(result)
    assert "我自己说" in _content(result) and "直接打字" in _content(result)


def test_selected_question_is_readonly_and_does_not_invent_a_selection() -> None:
    result = question_card("问题", why="依据", options=_actions(), selected_label="选项1")
    assert "你选了：选项1" in _content(result) and not _buttons(result)
    with pytest.raises(ValueError, match="本次问题"):
        question_card("问题", why="依据", options=_actions(), selected_label="伪造的选择")
    with pytest.raises(ValueError, match="四个"):
        question_card("问题", why="依据", options=_actions(5))


@pytest.mark.parametrize(
    "status", ["pending_confirmation", "stopped", "deleted", "rejected", "skipped", "failed", "undone"]
)
def test_unsaved_or_undone_receipts_cannot_claim_saved_or_offer_undo(status: str) -> None:
    result = memory_receipt_card((ReceiptLine("receipt", status, "SYNTHETIC_PRIVATE_SUMMARY"),))
    assert "记下了" not in _content(result) and not _buttons(result)
    assert "SYNTHETIC_PRIVATE_SUMMARY" not in result["config"]["summary"]["content"]
    with pytest.raises(ValueError, match="成功写入"):
        ReceiptLine("receipt", status, "合成摘要", _token(1))


def test_actual_undo_receipt_is_rendered_as_undone_and_never_replays_old_action() -> None:
    receipt = ReceiptLine("undo-receipt", "undone", "合成撤销结果")
    result = memory_receipt_card((receipt,))
    assert "已撤销：" in _content(result) and not _buttons(result)
    with pytest.raises(ValueError, match="状态"):
        ReceiptLine("receipt", "model_says_saved", "未经程序确认")


@pytest.mark.parametrize("category", ["health", "wellbeing", "finance", "money", "身心", "财务"])
def test_proactive_sensitive_preview_never_echoes_details_or_space(category: str) -> None:
    detail = f"SYNTHETIC_PRIVATE_{category}_DETAIL。"
    result = followup_card(detail, category=category)
    preview = result["config"]["summary"]["content"]
    assert detail not in preview and category not in preview
    assert detail in _content(result)


def test_brief_private_sections_are_not_promoted_to_lock_screen_preview() -> None:
    result = brief_card(
        date(2026, 10, 17),
        calendar="日期内容",
        plans="安排内容",
        daily_flow="流日内容",
        closing="结尾",
        sections=(BriefSection("身心", ("SYNTHETIC_PRIVATE_HEALTH",)),),
    )
    preview = result["config"]["summary"]["content"]
    assert "SYNTHETIC_PRIVATE_HEALTH" not in preview and "身心" not in preview
    assert "10月17日 周六" in result["header"]["title"]["content"]


def test_route_label_is_body_only_and_uses_two_distinct_callback_tokens() -> None:
    result = answer_card("回答", route=_route())
    assert "归入：身心·合成敏感话题" in _content(result)
    assert [button["text"]["content"] for button in _buttons(result)] == ["改区", "新话题"]
    tokens = [button["behaviors"][0]["value"]["t"] for button in _buttons(result)]
    assert len(set(tokens)) == 2
    assert "身心" not in result["config"]["summary"]["content"]
    assert route_card(_route())["config"]["summary"]["content"] == "对话归属"


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://app.example.invalid",
        "javascript:alert(1)",
        "data:text/html,x",
        "/me",
        "https://user:secret@app.example.invalid",
        "https://app.example.invalid:99999",
        "https://app.example.invalid\nHeader:x",
    ],
)
def test_app_links_require_explicit_valid_https_without_credentials(bad_url: str) -> None:
    with pytest.raises(ValueError):
        answer_card("回答", open_url=bad_url)


def test_explicit_app_link_is_used_verbatim_without_a_fabricated_deep_link() -> None:
    url = "https://app.example.invalid/#/me?view=synthetic"
    result = answer_card("回答", open_url=url)
    links = [
        behavior for button in _buttons(result) for behavior in button["behaviors"] if behavior["type"] == "open_url"
    ]
    assert len(links) == 1 and links[0]["default_url"] == url


def test_mutable_input_sequences_and_output_layout_are_not_shared() -> None:
    options = _actions()
    before = deepcopy(options)
    first = question_card("问题", why="依据", options=options)
    assert options == before
    options.clear()
    assert len(_buttons(first)) == 2
    first["body"]["elements"].clear()
    assert len(_buttons(question_card("问题", why="依据", options=before))) == 2


def test_literals_are_escaped_once_without_creating_markup_or_fake_links() -> None:
    text = "<at>&literal"
    escaped = literal(text)
    assert "<at>" not in escaped and "&amp;lt;" not in escaped
    assert "&lt;at" in escaped and "&amp;literal" in escaped
    result = question_card(text, why="[fake](javascript:synthetic)", options=())
    assert "<at>" not in _content(result) and "\\[fake\\]" in _content(result)


def test_streaming_placeholder_never_carries_final_actions_and_final_card_removes_status() -> None:
    initial = answer_card("", streaming=True)
    assert initial["config"]["streaming_mode"] is True
    assert {element.get("element_id") for element in _walk(initial["body"]["elements"])} == {"status", "answer"}
    with pytest.raises(ValueError, match="流式"):
        answer_card("", streaming=True, route=_route())
    final = answer_card("完成的正文", evidence="实际依据")
    assert final["config"]["streaming_mode"] is False
    assert all(element.get("element_id") != "status" for element in _walk(final["body"]["elements"]))

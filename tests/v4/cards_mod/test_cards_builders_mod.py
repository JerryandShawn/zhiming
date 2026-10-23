"""Design-level card assertions; these are candidate JSON tests, not official Feishu acceptance."""

import json
from copy import deepcopy
from datetime import date

import pytest

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


def token(number: int) -> str:
    return str(number).zfill(43)


def route() -> RouteLabel:
    return RouteLabel("事业学业", "合成求职话题", token(10), token(11))


def all_elements(card: dict) -> list[dict]:
    def flatten(elements: list[dict]) -> list[dict]:
        return [node for element in elements for node in [element, *flatten(element.get("elements", []))]]

    return flatten(card["body"]["elements"])


def choices(count: int) -> tuple[CardAction, ...]:
    return tuple(CardAction(f"选项{number}", token(number)) for number in range(count))


def candidates() -> list[dict]:
    return [
        answer_card("合成回答", route=route()),
        question_card("合成问题？", why="需要你确认", options=choices(3)),
        memory_receipt_card([ReceiptLine("r1", "saved", "合成偏好", token(20))]),
        proposal_card("合成记忆提案", remember_token=token(30), decline_token=token(31), always_token=token(32)),
        followup_card("最近还顺利吗？", replies=choices(2), category="health"),
        brief_card(
            date(2026, 10, 19),
            calendar="合成日期信息",
            plans="合成安排",
            daily_flow="合成流日句",
            closing="合成结尾",
            sections=[BriefSection("日常", ("合成近况",))],
        ),
        route_card(route()),
    ]


@pytest.mark.parametrize("candidate", candidates())
def test_all_seven_templates_are_json2_with_global_budget(candidate: dict) -> None:
    assert json.loads(json.dumps(candidate, ensure_ascii=False)) == candidate
    assert candidate["schema"] == "2.0" and candidate["header"]["template"] == "carmine"
    elements = all_elements(candidate)
    buttons = [element for element in elements if element["tag"] == "button"]
    assert len(buttons) <= 4
    for button in buttons:
        behavior = button["behaviors"][0]
        if behavior["type"] == "callback":
            assert set(behavior["value"]) == {"t"}
    assert candidate["config"]["streaming_mode"] is False


def test_stream_placeholder_and_final_have_stable_answer_id_and_different_layout() -> None:
    initial = answer_card("", streaming=True, status="正在核对合成资料")
    assert initial == {
        "schema": "2.0",
        "config": {"streaming_mode": True, "summary": {"content": "明镜正在回复…"}},
        "header": {"title": {"tag": "plain_text", "content": "明镜"}, "template": "carmine"},
        "body": {
            "elements": [
                {"tag": "markdown", "element_id": "status", "content": "正在核对合成资料"},
                {"tag": "markdown", "element_id": "answer", "content": ""},
            ]
        },
    }
    final = answer_card("最终合成回答", status="旧状态不会继续显示", evidence="象征依据", route=route())
    assert final["config"]["streaming_mode"] is False
    assert "status" not in {element.get("element_id") for element in all_elements(final)}
    assert all_elements(final)[0]["element_id"] == "answer"
    panel = next(element for element in all_elements(final) if element["tag"] == "collapsible_panel")
    assert panel["expanded"] is False and panel["header"]["title"]["content"] == "命理依据"


@pytest.mark.parametrize("length", [1501, 20_000])
def test_long_answer_keeps_full_content_in_collapsed_panel_without_inventing_url(length: int) -> None:
    body = "合" * length
    candidate = answer_card(body)
    assert all_elements(candidate)[0]["content"].startswith(body[:1200])
    assert any(element.get("content") == body for element in all_elements(candidate))
    assert not [element for element in all_elements(candidate) if element["tag"] == "button"]


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4])
def test_question_offers_free_text_and_consumed_question_removes_all_buttons(count: int) -> None:
    candidate = question_card("问题？", why="原因", options=choices(count))
    assert "也可以直接打字告诉我" in json.dumps(candidate, ensure_ascii=False)
    if count:
        selected = question_card("问题？", why="原因", options=choices(count), selected_label="选项0")
        assert not [element for element in all_elements(selected) if element["tag"] == "button"]
        assert "你选了：选项0" in json.dumps(selected, ensure_ascii=False)


@pytest.mark.parametrize(
    "status,label",
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
def test_receipt_status_is_not_promoted_to_success(status: str, label: str) -> None:
    candidate = memory_receipt_card([ReceiptLine("r1", status, "合成摘要")])
    assert candidate["body"]["elements"][0]["content"] == f"{label}：合成摘要"
    assert not [element for element in all_elements(candidate) if element["tag"] == "button"]


def test_full_answer_budget_allows_route_two_undo_one_app_one() -> None:
    receipt = ReceiptLine("r1", "saved", "合成偏好", token(20))
    candidate = answer_card("合成回答", receipts=[receipt], route=route(), open_url="https://synthetic.example/#/me")
    buttons = [element for element in all_elements(candidate) if element["tag"] == "button"]
    assert len(buttons) == 4
    with pytest.raises(ValueError, match="操作过多"):
        answer_card(
            "合成回答",
            receipts=[receipt, ReceiptLine("r2", "saved", "合成偏好2", token(21))],
            route=route(),
            open_url="https://synthetic.example/#/me",
        )


def test_builders_do_not_mutate_shared_envelope() -> None:
    options = list(choices(3))
    receipts = [ReceiptLine("r1", "saved", "合成偏好", token(20))]
    before = deepcopy((options, receipts))
    first = question_card("问题？", why="原因", options=options)
    answer_card("合成回答", receipts=receipts)
    assert (options, receipts) == before
    first["body"]["elements"].clear()
    assert question_card("问题？", why="原因", options=options)["body"]["elements"]


def test_brief_uses_owner_supplied_date_weekday_and_space_sections() -> None:
    candidate = brief_card(
        date(2026, 10, 19),
        calendar="合成农历/节气",
        plans="合成安排",
        daily_flow="合成流日句",
        closing="合成结尾",
        sections=[BriefSection("家庭", ("合成近况",))],
    )
    assert candidate["header"]["title"]["content"] == "10月19日 周一 · 晨报"
    assert any(element.get("element_id") == "space_0" for element in all_elements(candidate))
    assert all_elements(candidate)[-1]["content"] == "想聊聊，直接回复我就好。"


def test_long_brief_folds_without_losing_text_or_leaking_it_into_preview() -> None:
    body = "敏感合成正文" * 200
    candidate = brief_card(date(2026, 10, 19), calendar="日期", plans=body, daily_flow="流日", closing="结尾")
    assert any(body in element.get("content", "") for element in all_elements(candidate))
    assert "敏感" not in candidate["config"]["summary"]["content"]

"""JSON 2.0 candidate elements. 全部外部字段待对照飞书官方文档核实。"""

import re
from collections.abc import Sequence
from typing import Any

from mingjing_core.adapters.channels.cards_contracts import (
    RECEIPT_LABELS,
    CardAction,
    ReceiptLine,
    RouteLabel,
    app_url,
    text_value,
)

CardJSON = dict[str, Any]


def literal(value: str) -> str:
    escaped = value.replace("&", "&amp;").replace("<", "&lt;")
    return re.sub(r"([\\`*_\[\]{}()#!|>])", r"\\\1", escaped)


def markdown(value: str, element_id: str) -> CardJSON:
    # markdown/content/element_id：待对照飞书官方文档核实。
    return {"tag": "markdown", "element_id": element_id, "content": value}


def action_button(action: CardAction) -> CardJSON:
    # behaviors/callback/value 及 button type：待对照飞书官方文档核实。
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": action.label},
        "type": "primary" if action.primary else "default",
        "behaviors": [{"type": "callback", "value": {"t": action.token}}],
    }


def link_button(label: str, url: str) -> CardJSON:
    # open_url/default_url 是离线候选布局，待对照飞书官方文档核实。
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": "default",
        "behaviors": [{"type": "open_url", "default_url": app_url(url)}],
    }


def folded(value: str, title: str, element_id: str) -> CardJSON:
    # collapsible_panel/header/expanded：待对照飞书官方文档核实，不声明飞书已可接受。
    return {
        "tag": "collapsible_panel",
        "expanded": False,
        "header": {"title": {"tag": "plain_text", "content": title}},
        "elements": [markdown(value, element_id)],
    }


def receipt_elements(receipts: Sequence[ReceiptLine]) -> list[CardJSON]:
    if len({receipt.receipt_id for receipt in receipts}) != len(receipts):
        raise ValueError("记忆回执重复")
    result = []
    for index, receipt in enumerate(receipts):
        result.append(markdown(f"{RECEIPT_LABELS[receipt.status]}：{literal(receipt.summary)}", f"receipt_{index}"))
        if receipt.undo_token is not None:
            result.append(action_button(CardAction("撤销", receipt.undo_token)))
    return result


def route_elements(route: RouteLabel) -> list[CardJSON]:
    return [
        markdown(f"归入：{literal(route.space)}·{literal(route.topic)}", "route"),
        action_button(CardAction("改区", route.change_token)),
        action_button(CardAction("新话题", route.new_topic_token)),
    ]


def _layout_values(elements: Sequence[CardJSON]) -> tuple[list[CardJSON], list[str]]:
    buttons, ids = [], []
    for element in elements:
        if element["tag"] == "button":
            buttons.append(element)
        if "element_id" in element:
            ids.append(element["element_id"])
        if "elements" in element:
            nested_buttons, nested_ids = _layout_values(element["elements"])
            buttons.extend(nested_buttons)
            ids.extend(nested_ids)
    return buttons, ids


def card(title: str, elements: list[CardJSON], *, preview: str, streaming: bool = False) -> CardJSON:
    buttons, ids = _layout_values(elements)
    if len(buttons) > 4 or sum(button["type"] == "primary" for button in buttons) > 1:
        raise ValueError("卡片操作过多，请在主线选择至多四个按钮及一个主操作")
    tokens = [b["behaviors"][0]["value"]["t"] for b in buttons if b["behaviors"][0]["type"] == "callback"]
    if len(tokens) != len(set(tokens)) or len(ids) != len(set(ids)):
        raise ValueError("卡片操作凭证或元素标识重复")
    # schema/config/summary/header.template/body：待对照飞书官方文档核实。
    return {
        "schema": "2.0",
        "config": {"streaming_mode": streaming, "summary": {"content": text_value(preview, maximum=160)}},
        "header": {"title": {"tag": "plain_text", "content": text_value(title, maximum=80)}, "template": "carmine"},
        "body": {"elements": elements},
    }

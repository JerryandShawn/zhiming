"""Literal rendering from original typed inputs, following design 26's source transcription."""

from collections.abc import Sequence
from typing import Any

from mingjing_core.adapters.channels.cards_contracts import (
    RECEIPT_LABELS,
    CardAction,
    ReceiptLine,
    RouteLabel,
    app_url,
)

CardJSON = dict[str, Any]
# 已核实（26）：https://open.feishu.cn/document/feishu-cards/card-json-v2-components/content-components/rich-text
# Ampersand/pipe encoding is a conservative project policy; platform behavior remains a stage unknown.
_ENTITIES = {
    ">": "&#62;",
    "<": "&#60;",
    "*": "&#42;",
    "_": "&#95;",
    "~": "&sim;",
    "`": "&#96;",
    "[": "&#91;",
    "]": "&#93;",
    "(": "&#40;",
    ")": "&#41;",
    "#": "&#35;",
    "!": "&#33;",
    "\\": "&#92;",
    "&": "&#38;",
    "|": "&#124;",
    "-": "&#45;",
}


def literal(value: str) -> str:
    """Escape once from the original string, never reverse an older escaped JSON body."""
    return "".join(_ENTITIES.get(char, char) for char in value)


def markdown(content: str, element_id: str) -> CardJSON:
    return {"tag": "markdown", "element_id": element_id, "content": content}


def action_button(action: CardAction) -> CardJSON:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": action.label},
        "type": "primary" if action.primary else "default",
        "behaviors": [{"type": "callback", "value": {"t": action.token}}],
    }


def link_button(label: str, url: str) -> CardJSON:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": "default",
        "behaviors": [{"type": "open_url", "default_url": app_url(url)}],
    }


def receipt_elements(receipts: Sequence[ReceiptLine]) -> list[CardJSON]:
    if any(not isinstance(item, ReceiptLine) for item in receipts):
        raise ValueError("card_receipt_type_invalid")
    if len({item.receipt_id for item in receipts}) != len(receipts):
        raise ValueError("card_receipt_duplicate")
    result = []
    for index, item in enumerate(receipts):
        result.append(markdown(f"{RECEIPT_LABELS[item.status]}：{literal(item.summary)}", f"receipt_{index}"))
        if item.undo_token is not None:
            result.append(action_button(CardAction("撤销", item.undo_token)))
    return result


def route_elements(route: RouteLabel) -> list[CardJSON]:
    if not isinstance(route, RouteLabel):
        raise ValueError("card_route_type_invalid")
    return [
        markdown(f"归入：{literal(route.space)}·{literal(route.topic)}", "route"),
        action_button(CardAction("改区", route.change_token)),
        action_button(CardAction("新话题", route.new_topic_token)),
    ]

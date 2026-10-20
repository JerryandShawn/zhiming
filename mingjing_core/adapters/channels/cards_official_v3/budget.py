"""Preserve mandatory actions/receipts while shortening only explicitly optional body text."""

from .elements import CardJSON
from .validation import validate_card


def finish(
    title: str,
    elements: list[CardJSON],
    *,
    preview: str,
    streaming: bool = False,
    shorten_ids: tuple[str, ...] = (),
) -> CardJSON:
    # 已核实（26）：https://open.feishu.cn/document/feishu-cards/card-json-v2-structure
    card = {
        "schema": "2.0",
        "config": {"streaming_mode": streaming, "update_multi": True, "summary": {"content": preview}},
        "header": {"title": {"tag": "plain_text", "content": title}, "template": "carmine"},
        "body": {"elements": elements},
    }
    validated = validate_card(card, enforce_budget=False)
    try:
        return validate_card(validated)
    except ValueError as error:
        if str(error) != "card_byte_budget_exceeded" or not shorten_ids:
            raise
    eligible = [item for item in validated["body"]["elements"] if item.get("element_id") in shorten_ids]
    if not eligible:
        raise ValueError("card_byte_budget_exceeded")
    # Deterministic bounded search. No receipt, callback or business status is removed.
    originals = [item["content"] for item in eligible]
    for limit in (1200, 600, 300, 120, 40):
        for item, original in zip(eligible, originals, strict=True):
            if len(original) > limit:
                item["content"] = original[:limit] + "\n（内容已缩略，完整内容见明镜台）"
        try:
            return validate_card(validated)
        except ValueError as error:
            if str(error) != "card_byte_budget_exceeded":
                raise
    raise ValueError("card_byte_budget_exceeded")

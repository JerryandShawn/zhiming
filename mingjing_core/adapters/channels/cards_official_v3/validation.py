"""Strict local JSON/layout limits; document conformance is not a platform acceptance claim."""

import json
from collections.abc import Mapping
from typing import Any

from mingjing_core.adapters.channels.card_limits_official_v3 import (
    MAX_COMPONENTS,
    MAX_SEQUENCE,
    MAX_WIRE_BYTES,
    SAFE_CARD_BYTES,
    validate_element_id,
)
from mingjing_core.adapters.channels.cards_contracts import app_url, text_value, token_value
from mingjing_core.streaming.event_errors import EventValidationError
from mingjing_core.streaming.json_values import json_object

CardJSON = dict[str, Any]


def encoded_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def card_sizes(document: CardJSON) -> tuple[int, int]:
    inner = encoded_json(document)
    # Largest project finalize envelope. Nested JSON escapes quotes/backslashes a second time.
    wire = {"card": {"type": "card_json", "data": inner}, "uuid": "f" * 40, "sequence": MAX_SEQUENCE}
    return len(inner.encode("utf-8")), len(encoded_json(wire).encode("utf-8"))


def _button(element: CardJSON, tokens: list[str], styles: list[str]) -> None:
    label = element.get("text")
    if not isinstance(label, dict) or label.get("tag") != "plain_text":
        raise ValueError("card_button_label_invalid")
    text_value(label.get("content"), maximum=40)
    style = element.get("type")
    if style not in {"primary", "default"}:
        raise ValueError("card_button_style_invalid")
    styles.append(style)
    behaviors = element.get("behaviors")
    if not isinstance(behaviors, list) or len(behaviors) != 1 or not isinstance(behaviors[0], dict):
        raise ValueError("card_button_behavior_invalid")
    action = behaviors[0]
    if action.get("type") == "callback":
        value = action.get("value")
        if not isinstance(value, dict) or set(value) != {"t"}:
            raise ValueError("card_button_token_invalid")
        tokens.append(token_value(value["t"]))
    elif action.get("type") == "open_url":
        if app_url(action.get("default_url")) is None:
            raise ValueError("card_button_url_invalid")
    else:
        raise ValueError("card_button_behavior_invalid")


def _layout(elements: object) -> None:
    if not isinstance(elements, list) or not elements:
        raise ValueError("card_body_elements_required")
    stack, ids, tokens, styles, count = list(elements), [], [], [], 0
    while stack:
        item = stack.pop()
        count += 1
        if count > MAX_COMPONENTS or not isinstance(item, dict):
            raise ValueError("card_component_limit")
        if "element_id" in item:
            ids.append(validate_element_id(item["element_id"]))
        tag = item.get("tag")
        if tag == "markdown":
            text_value(item.get("content"), maximum=100_000)
        elif tag == "button":
            _button(item, tokens, styles)
        elif tag == "collapsible_panel":
            if type(item.get("expanded")) is not bool or not isinstance(item.get("elements"), list):
                raise ValueError("card_panel_invalid")
            title = item.get("header", {}).get("title", {})
            if title.get("tag") != "plain_text":
                raise ValueError("card_panel_title_invalid")
            text_value(title.get("content"), maximum=80)
            stack.extend(item["elements"])
        else:
            raise ValueError("card_component_unsupported")
    if len(ids) != len(set(ids)) or len(tokens) != len(set(tokens)):
        raise ValueError("card_duplicate_identity")
    if len(styles) > 4 or styles.count("primary") > 1:
        raise ValueError("card_action_limit")


def validate_card(document: Mapping[str, object], *, enforce_budget: bool = True) -> CardJSON:
    """Return an isolated JSON object; reject unsupported/oversized local candidate layouts."""
    try:
        copied = json_object(document)
        config, header, body = copied.get("config"), copied.get("header"), copied.get("body")
        if copied.get("schema") != "2.0" or not all(isinstance(x, dict) for x in (config, header, body)):
            raise ValueError("card_envelope_invalid")
        if config.get("update_multi") is not True or type(config.get("streaming_mode")) is not bool:
            raise ValueError("card_config_invalid")
        summary = config.get("summary")
        title = header.get("title")
        if not isinstance(summary, dict) or not isinstance(title, dict) or title.get("tag") != "plain_text":
            raise ValueError("card_header_invalid")
        text_value(summary.get("content"), maximum=160)
        text_value(title.get("content"), maximum=80)
        _layout(body.get("elements"))
        inner, wire = card_sizes(copied)
        if enforce_budget and (inner > SAFE_CARD_BYTES or wire > MAX_WIRE_BYTES):
            raise ValueError("card_byte_budget_exceeded")
        return copied
    except (EventValidationError, AttributeError, TypeError, RecursionError, UnicodeError):
        raise ValueError("card_json_invalid") from None

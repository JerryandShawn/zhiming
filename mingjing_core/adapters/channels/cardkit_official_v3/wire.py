"""Offline request descriptions only; links/dates are transcribed from design 26."""

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from mingjing_core.adapters.channels.card_limits_official_v3 import (
    MAX_WIRE_BYTES,
    validate_card_id,
    validate_element_id,
    validate_sequence,
    wire_uuid,
)
from mingjing_core.adapters.channels.cardkit_contracts import canonical
from mingjing_core.streaming.json_values import json_object, thaw_json

from .contracts import ArtifactEvidence, OfficialError, OfficialRequest, OfficialState

BASE = "/open-apis/cardkit/v1/cards"

# 已核实：26号2026-10-20转录；本模块未访问业务接口。日期是官方文档更新日期。
# create: https://open.feishu.cn/document/cardkit-v1/card/create (2025-07-03).
# send: https://open.feishu.cn/document/server-docs/im-v1/message/create (2026-04-10).
# update: https://open.feishu.cn/document/cardkit-v1/card-element/content (2025-08-22).
# finalize: https://open.feishu.cn/document/cardkit-v1/card/update (2025-07-03).
# close_streaming: https://open.feishu.cn/document/cardkit-v1/card/settings (2025-08-05).


def initial_card() -> dict[str, Any]:
    # 初始空组件官方未说明，stage 实测项；本包装固定非空状态，不接受私密任意占位正文。
    from mingjing_core.adapters.channels.cards_official_v3 import answer_card

    return answer_card("", streaming=True)


def _card(value: Mapping[str, Any]) -> dict[str, Any]:
    from mingjing_core.adapters.channels.cards_official_v3 import validate_card

    return validate_card(json_object(value))


def build_wire_request(
    state: OfficialState,
    kind: str,
    payload: Any,
    *,
    operation_id: str,
    sequence: int | None,
    artifact: ArtifactEvidence,
    element_id: str = "answer",
) -> OfficialRequest:
    uuid = wire_uuid(operation_id)
    query, body, path, method = {}, {}, BASE, "POST"
    if kind == "create":
        if payload is not None and json_object(payload) != initial_card():
            raise OfficialError("fixed_initial_card_required")
        body = {"type": "card_json", "data": canonical(_card(initial_card()))}
    elif kind == "send":
        if payload is not None:
            raise OfficialError("send_content_is_bound_card_entity")
        card = validate_card_id(state.card_id)
        path = "/open-apis/im/v1/messages"
        query = {"receive_id_type": "open_id"}
        body = {
            "receive_id": state.scope.target,
            "msg_type": "interactive",
            "uuid": uuid,
            "content": canonical({"type": "card", "data": {"card_id": card}}),
        }
    elif kind == "update":
        validate_element_id(element_id)
        if type(payload) is not str or not 1 <= len(payload) <= 100_000:
            raise OfficialError("stream_text_length_invalid")
        path, method = f"{BASE}/{quote(validate_card_id(state.card_id), safe='')}/elements/{element_id}/content", "PUT"
        body = {"content": payload, "uuid": uuid, "sequence": validate_sequence(sequence)}
    elif kind == "finalize":
        layout = _card(payload)
        if layout != thaw_json(artifact.final_card):
            raise OfficialError("final_card_not_authorized_artifact")
        path, method = f"{BASE}/{quote(validate_card_id(state.card_id), safe='')}", "PUT"
        body = {
            "card": {"type": "card_json", "data": canonical(layout)},
            "uuid": uuid,
            "sequence": validate_sequence(sequence),
        }
    elif kind == "close_streaming":
        if payload is not None:
            raise OfficialError("close_settings_derived_from_artifact")
        summary = _card(artifact.final_card)["config"]["summary"]
        path, method = f"{BASE}/{quote(validate_card_id(state.card_id), safe='')}/settings", "PATCH"
        body = {
            "settings": canonical({"config": {"streaming_mode": False, "summary": summary}}),
            "uuid": uuid,
            "sequence": validate_sequence(sequence),
        }
    else:
        raise OfficialError("wire_kind_invalid")
    _budget({"method": method, "path": path, "query": query, "body": body})
    return OfficialRequest(kind, method, path, query, body, operation_id, uuid, sequence)


def _budget(body: Mapping[str, Any]) -> None:
    # 28K/30K decimal bytes is an engineering margin, not a claimed stage verification of platform KB units.
    try:
        if len(canonical(dict(body)).encode("utf-8")) > MAX_WIRE_BYTES:
            raise OfficialError("wire_body_too_large")
    except (UnicodeError, TypeError, ValueError):
        raise OfficialError("wire_body_invalid_or_too_large") from None


def request_data(request: OfficialRequest) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": request.path,
        "query": thaw_json(request.query),
        "body": thaw_json(request.body),
    }


def wire_payload(request: OfficialRequest) -> Any:
    body = thaw_json(request.body)
    if request.kind == "create":
        return json.loads(body["data"])
    if request.kind == "finalize":
        return json.loads(body["card"]["data"])
    return body.get("content") if request.kind == "update" else None

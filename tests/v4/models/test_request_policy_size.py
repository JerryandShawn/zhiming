"""Only serialized httpx bytes passing preflight may consume a physical attempt."""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest

from mingjing_core.models.errors import ModelBadRequest, ModelCancelled, ModelPayloadTooLarge, ModelProtocolError
from mingjing_core.models.metering import request_meter
from mingjing_core.models.port import ChatMessage, Part, ToolSpec
from mingjing_core.models.request_policy import DEFAULT_MAX_REQUEST_BYTES
from mingjing_core.models.transport import StreamingHTTP

from .test_request_policy_wire import PROTOCOLS, wire_model


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("kind", ["ascii", "utf8", "image", "schema"])
def test_default_limit_counts_every_final_wire_field_before_meter(protocol: type[StreamingHTTP], kind: str) -> None:
    private = "SYNTHETIC_PRIVATE_BODY"
    messages = [ChatMessage("user", private)]
    tools = None
    if kind in {"ascii", "utf8"}:
        messages = [ChatMessage("user", private + ("x" * 1_900_000 if kind == "ascii" else "测" * 650_000))]
    elif kind == "image":
        messages = [ChatMessage("user", [Part(type="image", data="A" * 1_900_000)])]
    else:
        tools = [ToolSpec("lookup", "合成", {"type": "object", "description": private + "x" * 1_900_000})]
    model, requests = wire_model(protocol)
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)), pytest.raises(ModelPayloadTooLarge) as caught:
        model.complete(messages, tools=tools)
    assert DEFAULT_MAX_REQUEST_BYTES == 1_800_000
    assert requests == [] and metered == []
    assert model.request_count == model.quota_errors == 0
    assert caught.value.kind == "payload_too_large" and caught.value.retry_actions.retry == "never"
    assert private not in str(caught.value) + json.dumps(caught.value.safe_diagnostic())
    assert caught.value.__cause__ is None and caught.value.__context__ is None


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("text", ["ascii", "合成中文🙂", '引号"、反斜线\\、换行\n、控制字符\x00'])
def test_exact_httpx_bytes_at_limit_send_and_one_byte_below_refuses(protocol: type[StreamingHTTP], text: str) -> None:
    model, requests = wire_model(protocol)
    metered: list[int] = []
    messages = [ChatMessage("user", text)]
    with request_meter(lambda: metered.append(1)):
        model.complete(messages)
        first = requests[0]
        size = len(first.content)
        model.settings["max_request_bytes"] = size
        model.complete(messages)
        assert requests[1].content == first.content
        assert requests[1].headers["Content-Type"] == "application/json"
        assert int(requests[1].headers["Content-Length"]) == size
        model.settings["max_request_bytes"] = size - 1
        with pytest.raises(ModelPayloadTooLarge):
            model.complete(messages)
    assert len(requests) == model.request_count == len(metered) == 2
    content = json.loads(first.content)["messages"][0]["content"]
    assert (content[0]["text"] if isinstance(content, list) else content) == text


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_configured_larger_byte_limit_uses_same_real_request(protocol: type[StreamingHTTP]) -> None:
    model, requests = wire_model(protocol, settings={"max_request_bytes": 2_000_000})
    model.complete([ChatMessage("user", "x" * 1_900_000)])
    assert DEFAULT_MAX_REQUEST_BYTES < len(requests[0].content) <= 2_000_000
    assert model.request_count == 1


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_non_k3_has_no_implicit_k3_byte_limit(protocol: type[StreamingHTTP]) -> None:
    model, requests = wire_model(protocol, model="portable-model")
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)):
        model.complete([ChatMessage("user", "x" * 1_900_000)])
    assert len(requests[0].content) > DEFAULT_MAX_REQUEST_BYTES
    assert len(requests) == model.request_count == len(metered) == 1


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_non_k3_explicit_byte_limit_is_enforced_before_meter(protocol: type[StreamingHTTP]) -> None:
    model, requests = wire_model(
        protocol, model="portable-model", settings={"max_request_bytes": DEFAULT_MAX_REQUEST_BYTES}
    )
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)), pytest.raises(ModelPayloadTooLarge):
        model.complete([ChatMessage("user", "x" * 1_900_000)])
    assert requests == [] and metered == [] and model.request_count == 0


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("model_name", ["k3-256k", "portable-model"])
@pytest.mark.parametrize("maximum", [None, False, 0, -1, 1.8, "1800000"])
def test_invalid_limit_cannot_disable_preflight(protocol: type[StreamingHTTP], model_name: str, maximum: Any) -> None:
    model, requests = wire_model(protocol, model=model_name, settings={"max_request_bytes": maximum})
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)), pytest.raises(ModelBadRequest):
        model.complete([ChatMessage("user", "合成")])
    assert requests == [] and metered == [] and model.request_count == 0


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_serialization_failure_is_safe_and_never_counted_as_a_post(protocol: type[StreamingHTTP]) -> None:
    model, requests = wire_model(protocol, settings={"max_output": float("nan")})
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)), pytest.raises(ModelProtocolError):
        model.complete([ChatMessage("user", "合成")])
    assert requests == [] and metered == [] and model.request_count == 0


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_cancelled_oversized_request_has_no_meter_or_post(protocol: type[StreamingHTTP]) -> None:
    model, requests = wire_model(protocol)
    cancel = threading.Event()
    cancel.set()
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)), pytest.raises(ModelCancelled):
        model.complete([ChatMessage("user", "x" * 1_900_000)], cancel_event=cancel)
    assert requests == [] and metered == [] and model.request_count == 0


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_meter_denial_happens_after_preflight_before_request_count(protocol: type[StreamingHTTP]) -> None:
    model, requests = wire_model(protocol)
    metered: list[int] = []

    def deny() -> None:
        metered.append(1)
        raise ModelBadRequest()

    with request_meter(deny), pytest.raises(ModelBadRequest):
        model.complete([ChatMessage("user", "合成")])
    assert requests == [] and metered == [1] and model.request_count == 0

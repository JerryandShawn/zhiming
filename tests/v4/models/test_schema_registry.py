"""Schema preservation and failover behavior are independent of live credentials."""

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from mingjing_core.domain.consultation import FinalAnswer, Intake
from mingjing_core.models.errors import (
    CapabilityError,
    ModelCancelled,
    ModelQuotaExhausted,
    ModelUnavailable,
)
from mingjing_core.models.legacy import PortBackedModel
from mingjing_core.models.port import ChatMessage
from mingjing_core.models.registry import ModelRegistry
from mingjing_core.models.schema_flatten import flatten_schema

from .test_protocols import CAPS, adapter, openai_record, recording


@pytest.mark.parametrize("contract", [Intake, FinalAnswer])
@pytest.mark.parametrize("dialect", ["openai", "openai_partial", "anthropic"])
def test_pydantic_contract_is_flattened_without_mutation(contract: Any, dialect: Any) -> None:
    source = contract.model_json_schema()
    before = json.dumps(source, sort_keys=True)
    flattened = flatten_schema(source, dialect)
    serialized = json.dumps(flattened)
    assert "$defs" not in serialized and "$ref" not in serialized and '"default"' not in serialized
    assert json.dumps(source, sort_keys=True) == before
    assert flattened["type"] == "object"
    assert "type" not in flattened["properties"]
    if contract is Intake:
        proposal = flattened["properties"]["proposals"]["items"]
        assert "field" not in proposal["required"]
    else:
        assert flattened["properties"]["decision_options"]["items"]["properties"]["risk"]["type"] == "string"


@pytest.mark.parametrize(
    "name,properties,required",
    [
        (
            "ask_user",
            {
                "question": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
                "allow_free_text": {"type": "boolean"},
                "why": {"type": "string"},
            },
            ["question", "allow_free_text", "why"],
        ),
        (
            "memory_write",
            {
                "message_id": {"type": "string"},
                "quote": {"type": "string"},
                "summary": {"type": "string"},
                "kind": {"type": "string"},
                "event_at": {"type": "string"},
            },
            ["message_id", "quote", "summary", "kind"],
        ),
    ],
)
def test_blueprint_tool_schemas(name: Any, properties: Any, required: Any) -> None:
    schema = {"type": "object", "properties": properties, "required": required}
    assert flatten_schema(schema)["required"] == required, name


def test_optional_any_and_escaped_local_reference() -> None:
    source = {
        "type": "object",
        "properties": {
            "maybe": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "anything": {},
            "named": {"$ref": "#/$defs/a~1b"},
        },
        "required": ["maybe", "anything", "named"],
        "$defs": {"a/b": {"type": "string", "format": "date"}},
    }
    result = flatten_schema(source)
    assert result["required"] == ["anything", "named"]
    assert "null" in result["properties"]["anything"]["type"]
    partial = flatten_schema(source, "openai_partial")
    assert partial["properties"]["anything"]["type"] == "string"
    assert "JSON" in partial["properties"]["anything"]["description"]


@pytest.mark.parametrize(
    "schema,dialect",
    [
        ({"$ref": "https://example.invalid"}, "openai"),
        ({"$defs": {"x": {"$ref": "#/$defs/x"}}, "$ref": "#/$defs/x"}, "openai"),
        ({}, "unknown"),
    ],
)
def test_reject_remote_recursive_and_unknown_schema(schema: Any, dialect: Any) -> None:
    with pytest.raises(ValueError):
        flatten_schema(schema, dialect)


def registry(tmp_path: Any, *, shared: Any = False) -> Any:
    data = {
        "version": 1,
        "providers": {
            "one": {
                "protocol": "openai_compat",
                "api_key_env": "KEY1",
                "base_url": "https://one.invalid",
                "settings": {"membership": True},
            },
            "two": {"protocol": "openai_compat", "api_key_env": "KEY2", "base_url": "https://two.invalid"},
        },
        "models": {
            "a": {"provider": "one", "model": "a", "caps": CAPS},
            "sibling": {"provider": "two", "model": "sibling", "caps": CAPS},
            "b": {"provider": "two", "model": "b", "caps": CAPS},
        },
        "roles": {"primary": ["a", "sibling", "b"]},
    }
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return ModelRegistry(
        path, environment={"KEY1": "synthetic-one", "KEY2": "synthetic-one" if shared else "synthetic-two"}
    )


def test_provider_503_four_attempts_then_failover(tmp_path: Any) -> None:
    model_registry = registry(tmp_path)
    attempts = []

    def factory(handle: Any) -> Any:
        def respond(_: Any) -> Any:
            attempts.append(handle.model)
            if handle.model == "a":
                return httpx.Response(503, text="transient")
            return httpx.Response(
                200, content=recording({"choices": [{"delta": {"content": "成功"}, "finish_reason": "stop"}]})
            )

        model = adapter(respond, max_retries=0)
        model.model, model.provider = handle.model, handle.provider
        return model

    result = model_registry.port(factory=factory).complete([ChatMessage("user", "查询")])
    assert attempts == ["a", "a", "a", "a", "sibling"]
    assert (result.model, result.provider) == ("sibling", "two")


def test_quota_global_stop_and_shared_key_siblings(tmp_path: Any) -> None:
    calls = []

    class QuotaPort:
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            calls.append("quota")
            raise ModelQuotaExhausted(status=429)

    reg = registry(tmp_path, shared=True)
    port = reg.port(factory=lambda _: QuotaPort())
    with pytest.raises(ModelQuotaExhausted):
        port.complete([ChatMessage("user", "查询")])
    assert calls == ["quota"] and port.quota_errors == 1
    calls.clear()
    with pytest.raises(ModelQuotaExhausted):
        reg.port(factory=lambda _: QuotaPort(), stop_on_quota=True).complete([])
    assert calls == ["quota"]


@pytest.mark.parametrize("error", [CapabilityError, ModelCancelled])
def test_bad_request_or_cancel_does_not_fallback(tmp_path: Any, error: Any) -> None:
    calls = []

    class FailedPort:
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            calls.append(1)
            raise error()

    with pytest.raises(error):
        registry(tmp_path).port(factory=lambda _: FailedPort()).complete([])
    assert len(calls) == 1


def test_environment_fallback_disabled_and_warning_once(tmp_path: Any, caplog: Any) -> None:
    reg = registry(tmp_path)
    reg.environment = {}
    assert reg.resolve() == reg.resolve() == []
    assert len(caplog.records) == 3
    reg.environment = {"KEY1": "synthetic-value"}
    reg.data["providers"]["one"]["enabled"] = False
    assert reg.resolve() == []
    reg.data["providers"]["one"].update(
        enabled=True, api_key_env="MISSING", api_key_fallback_env="KEY1", base_url_env="CUSTOM_BASE"
    )
    reg.environment = {"KEY1": "synthetic-value", "CUSTOM_BASE": "https://custom.invalid"}
    handle = reg.resolve()[0]
    assert handle.base_url == "https://custom.invalid" and "synthetic-value" not in repr(handle)
    assert handle.adapter().model == "a"
    assert reg.resolve("embedding") == []


def test_v3_submit_shim_and_usage_mapping(tmp_path: Any) -> None:
    reg = registry(tmp_path)
    reg.data["roles"]["primary"] = ["a"]
    model = PortBackedModel(reg)
    bodies = []

    def respond(request: Any) -> Any:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=openai_record('{"answer":"合成"}').replace(b"lookup", b"submit"))

    model.port = reg.port(factory=lambda _: adapter(respond))
    result = model.generate(
        system="合成系统", payload={"reference_data": {}}, schema={"type": "object"}, purpose="intake"
    )
    assert result["output"] == {"answer": "合成"} and result["usage"]["input_tokens"] == 3
    assert bodies[0]["max_tokens"] == 6000
    assert bodies[0]["tool_choice"]["function"]["name"] == "submit"


def test_default_registry_loads_no_network() -> None:
    root = Path(__file__).resolve().parents[3]
    reg = ModelRegistry(
        root / "config/models.yaml", environment={"KIMI_API_KEY": "synthetic-value", "KIMI_MODEL": "k3"}
    )
    assert [handle.model for handle in reg.resolve()] == ["k3-256k"]
    assert reg.resolve("critic")[0].model == "k3-256k"
    assert reg.resolve("fast")[0].provider == "kimi_code"


def test_registry_shares_total_deadline_across_retries_and_providers(tmp_path: Any) -> None:
    reg = registry(tmp_path)
    reg.data["providers"]["one"]["settings"]["total_timeout"] = 0.01
    attempts: list[str] = []

    def factory(handle: Any) -> Any:
        def respond(_: httpx.Request) -> httpx.Response:
            attempts.append(handle.model)
            time.sleep(0.03)
            return httpx.Response(
                200, content=recording({"choices": [{"delta": {"content": "too late"}, "finish_reason": "stop"}]})
            )

        return adapter(respond, max_retries=0)

    with pytest.raises(ModelUnavailable):
        reg.port(factory=factory).complete([])
    assert attempts == ["a"]

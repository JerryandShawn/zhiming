"""Single-submit membership calls cannot retain obsolete wire controls or bypass U39."""

from __future__ import annotations

import copy
import json
from typing import Any

import httpx
import pytest

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.errors import CapabilityError, ModelBadRequest
from mingjing_core.models.legacy_request_policy import (
    LegacyConversationUnsupported,
    configured_model,
    member_body,
)
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_legacy import post_legacy
from mingjing_core.repositories.postgres import PostgresRepository

from .test_quota_guard_pg import configure_central
from .test_quota_http_pg import rows


def body() -> dict[str, Any]:
    return {
        "model": "k3-256k",
        "system": "synthetic",
        "messages": [{"role": "user", "content": "synthetic"}],
        "tools": [{"name": "submit", "description": "synthetic", "input_schema": {"type": "object"}}],
        "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
        "max_tokens": 6000,
        "thinking": {"type": "enabled", "budget_tokens": 1024},
        "temperature": 1,
        "top_p": 1,
    }


def test_legacy_member_wire_uses_documented_auto_high_and_current_tool_policy() -> None:
    original = body()
    before = copy.deepcopy(original)
    normalized = member_body(original, model="k3-256k", role="critic")
    assert original == before
    assert not {"thinking", "temperature", "top_p", "effort", "reasoning_effort"} & normalized.keys()
    assert normalized["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}


@pytest.mark.parametrize(
    "controls",
    [
        {"thinking": {"type": "disabled"}},
        {"thinking": False},
        {"effort": "none"},
        {"reasoning_effort": "low"},
        {"output_config": {"effort": "low"}},
        {"tool_choice": {"type": "none"}},
        {"tool_choice": {"type": "tool", "name": "submit"}},
        {"model": "k3"},
    ],
)
def test_obsolete_or_disabled_controls_fail_closed(controls: dict[str, Any]) -> None:
    with pytest.raises((ConfigError, CapabilityError, ModelBadRequest)):
        member_body(body() | controls, model="k3-256k", role="primary")


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "assistant", "content": "hidden"}],
        [{"role": "tool", "content": "result"}],
        [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "next"},
        ],
        [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "old", "content": "result"}]}],
        [{"role": "user", "content": "next", "reasoning": "old"}],
    ],
)
def test_legacy_history_requires_canonical_model_port(messages: list[dict[str, Any]]) -> None:
    with pytest.raises(LegacyConversationUnsupported):
        member_body(body() | {"messages": messages}, model="k3-256k", role="primary")


def test_member_default_ignores_old_user_environment_but_explicit_history_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIMI_MODEL", "k3")
    monkeypatch.delenv("KIMI_BASE_URL", raising=False)
    model = ConfiguredModel(key="synthetic")
    assert model.base == "https://api.kimi.com/coding/v1" and model.model == "k3-256k"
    assert ConfiguredModel(key="synthetic", model="k3").model == "k3"
    assert configured_model("https://other.invalid", None, "other-model") == "other-model"


def test_central_pg_records_only_sanitized_legacy_wire_and_refuses_history_before_post(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = QuotaGuard(**configure_central(p2_repo, monkeypatch))
    sent = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"usage": {"input_tokens": 2, "output_tokens": 1}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        post_legacy(
            client,
            base="https://api.kimi.com/coding/v1",
            model="k3-256k",
            role="primary",
            headers={},
            body=body(),
            guard=guard,
        )
        with pytest.raises(LegacyConversationUnsupported):
            post_legacy(
                client,
                base="https://api.kimi.com/coding/v1",
                model="k3-256k",
                role="primary",
                headers={},
                body=body() | {"messages": [{"role": "assistant", "content": "old"}]},
                guard=guard,
            )
        for invalid in ({"thinking": False}, {"effort": "low"}, {"tool_choice": {"type": "none"}}):
            with pytest.raises((ConfigError, CapabilityError)):
                post_legacy(
                    client,
                    base="https://api.kimi.com/coding/v1",
                    model="k3-256k",
                    role="primary",
                    headers={},
                    body=body() | invalid,
                    guard=guard,
                )
    assert len(sent) == len(rows(guard)) == 1
    assert "thinking" not in sent[0] and sent[0]["tool_choice"]["type"] == "any"
    assert rows(guard)[0]["status"] == "ok" and guard.status()["in_flight"] == 0

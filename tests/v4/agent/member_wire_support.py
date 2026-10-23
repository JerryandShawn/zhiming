"""Synthetic provider bytes traverse the real combined Runtime and PG account guard."""

from __future__ import annotations

from typing import Any

import httpx
from models.test_u39_anthropic_wire import block_record

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.quota_guard import QuotaGuard


class OfflineMember(AnthropicMessages):
    offline = True


def member_port(guard: QuotaGuard, handler: Any, *, role: str = "primary", **settings: Any) -> OfflineMember:
    return OfflineMember(
        base_url="https://synthetic.invalid/v1",
        api_key="synthetic-only",
        model="k3-256k",
        provider="kimi_code",
        caps={"tools": True, "reasoning_replay": True, "sampling_fixed": True},
        settings={"membership": True, "role_binding": role, "effort": "high", **settings},
        transport=httpx.MockTransport(handler),
        guard=guard,
        max_retries=0,
        sleep=lambda _: None,
    )


def response(text: str = "合成普通答复") -> httpx.Response:
    return httpx.Response(200, content=block_record([{"type": "text", "text": text}]))

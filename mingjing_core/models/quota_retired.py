"""Retired controllers retain offline regressions; physical model HTTP is disabled."""

from __future__ import annotations

from typing import Any

import httpx

from .errors import ModelBadRequest


class RetiredProviderDisabled(ModelBadRequest):
    code = "RETIRED_PROVIDER_DISABLED"


def assert_retired_offline(client: Any) -> None:
    transport = getattr(client, "_transport", None)
    if isinstance(transport, httpx.MockTransport):
        return
    if transport is None and getattr(client, "_zhiming_offline_transport", False) is True:
        return
    raise RetiredProviderDisabled("退役控制器不允许真实模型请求，请使用当前Core入口")


async def retired_post(client: Any, url: str, **kwargs: Any) -> Any:
    assert_retired_offline(client)
    return await client.post(url, **kwargs)

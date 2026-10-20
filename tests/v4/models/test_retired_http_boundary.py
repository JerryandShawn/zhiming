"""Retired algorithms can exercise explicit offline I/O, never an actual HTTP transport."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from mingjing_core.models.quota_retired import RetiredProviderDisabled, assert_retired_offline, retired_post


def test_real_async_transport_is_blocked_even_with_offline_marker() -> None:
    client = httpx.AsyncClient()
    client._zhiming_offline_transport = True
    try:
        with pytest.raises(RetiredProviderDisabled):
            assert_retired_offline(client)
    finally:
        asyncio.run(client.aclose())


def test_actual_mock_transport_can_exercise_offline_algorithm() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
            assert (await retired_post(client, "https://synthetic.invalid", json={})).status_code == 200

    asyncio.run(run())


def test_unknown_duck_client_is_not_assumed_offline() -> None:
    class Unknown:
        async def post(self, *args: Any, **kwargs: Any) -> None:
            pytest.fail("unknown transport must not run")

    with pytest.raises(RetiredProviderDisabled):
        asyncio.run(retired_post(Unknown(), "https://synthetic.invalid"))

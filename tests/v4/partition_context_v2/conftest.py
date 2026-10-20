"""This suite never needs credentials or outbound connections."""

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    def denied(*args, **kwargs):
        raise AssertionError("partition_context_offline_only")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)

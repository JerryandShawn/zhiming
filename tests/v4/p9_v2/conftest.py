"""P9 candidates use synthetic metadata and injected transports exclusively."""

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_p9_v2(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("P9纯模块不得发起外部连接")

    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

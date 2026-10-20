"""Cross-module demonstrations remain local and use synthetic source snapshots exclusively."""

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_composition(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("组合验证不得访问网络")

    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

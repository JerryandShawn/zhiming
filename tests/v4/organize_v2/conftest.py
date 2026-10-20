"""No optional encoder may use the network while the synthetic module candidate is tested."""

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_organize_candidate(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("纯整理候选不得发起网络请求")

    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

"""Date and profile parsers use only frozen local calendar data and injected synthetic profiles."""

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_date_extensions(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("日期扩展不得访问网络")

    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

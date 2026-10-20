"""Scheduling is pure: all calendar data is local and no delivery transport is called."""

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_scheduling(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("纯调度模块不得发起网络请求")

    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

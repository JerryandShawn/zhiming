"""One web window: no phantom conversations, and the shared history merges every conversation.

Users reported the web chat "opening another conversation". Automatic privacy-mode state is
stored with the 'session' kind, so /api/sessions listed it as an untitled conversation. The new
page shows one continuous timeline (/api/history?session=shared); stored data is not moved.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app
from mingjing_core.application.threads import ThreadService
from mingjing_core.repositories.postgres import PostgresRepository

from .test_privacy_mode_pg import receive
from .test_thread_inbox_pg import set_runtime

HEADERS = {"X-Token": "synthetic-single-window-token"}


@pytest.fixture(name="window_repo")
def window_repo_fixture(p2_repo: PostgresRepository) -> Iterator[PostgresRepository]:
    # Not the loop-cycle fixture: it blocks httpx, which the in-process TestClient needs.
    p2_repo.bind_channel("alice", "web", "author")
    yield p2_repo


@pytest.fixture(name="client")
def client_fixture(window_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MINGJING_TOKEN", HEADERS["X-Token"])
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.delenv("ZHIMING_TOKEN_OWNERS", raising=False)
    service: Any = SimpleNamespace(repo=window_repo)
    return TestClient(create_app(service=service))


def test_privacy_mode_state_is_not_listed_as_a_conversation(window_repo: PostgresRepository, client) -> None:
    set_runtime(window_repo, "v4")
    receive(window_repo, "开个无痕", "enter", conversation_id="shared")
    receive(window_repo, "结束无痕", "exit", conversation_id="shared")
    states = [row for row in window_repo.list("alice", "session") if row["id"].startswith("privacy-mode:")]
    assert len(states) == 1 and states[0]["ingress"] == "privacy_mode"
    created = client.post("/api/sessions", json={"request_id": "synthetic-old-session"}, headers=HEADERS)
    assert created.status_code == 200, created.text
    listed = client.get("/api/sessions", headers=HEADERS)
    assert listed.status_code == 200
    assert [(row["id"], row["title"]) for row in listed.json()] == [("synthetic-old-session", "新的对话")]


def test_shared_history_merges_every_old_conversation_without_moving_data(
    window_repo: PostgresRepository, client
) -> None:
    threads = ThreadService(window_repo)
    thread = threads.create("alice", request_id="life:self")["id"]
    for request, conversation in (("first", "old-one"), ("second", "old-two"), ("third", "shared")):
        threads.receive("alice", thread, "合成原话" + request, request_id=request, conversation_id=conversation)
    before = {row["id"]: row["conversation_id"] for row in window_repo.list("alice", "message")}
    merged = client.get("/api/history", params={"session": "shared"}, headers=HEADERS)
    assert merged.status_code == 200
    assert [row["content"] for row in merged.json()] == ["合成原话first", "合成原话second", "合成原话third"]
    single = client.get("/api/history", params={"session": "old-two"}, headers=HEADERS).json()
    assert [row["content"] for row in single] == ["合成原话second"]
    assert {row["id"]: row["conversation_id"] for row in window_repo.list("alice", "message")} == before

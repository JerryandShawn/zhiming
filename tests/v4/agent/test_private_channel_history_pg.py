"""The authenticated legacy Feishu history endpoint also excludes private bodies."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app
from mingjing_core.application.threads import ThreadService
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock


def test_legacy_channel_history_keeps_normal_messages_only(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ThreadService(p2_repo, clock=FrozenClock(datetime.fromisoformat("2026-10-17T08:30:00+08:00")))
    life = service.create("alice", request_id="normal-synthetic")
    private = service.create("alice", incognito=True, request_id="private-synthetic")
    normal = service.receive("alice", life["id"], "合成普通渠道原话", request_id="normal-message")
    hidden = service.receive("alice", private["id"], "合成无痕渠道原话", request_id="private-message")
    # Synthetic fixture channel labels; no gateway, sender or provider is constructed.
    for row in (normal, hidden):
        p2_repo.update("alice", "message", row["id"], {"channel": "feishu"}, expected_revision=row["revision"])
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-channel-history")
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    client = TestClient(create_app(SimpleNamespace(repo=p2_repo, memory=service.memory)))
    response = client.get("/api/feishu_history", headers={"X-Token": "synthetic-channel-history"})
    assert response.status_code == 200
    assert [row["content"] for row in response.json()] == ["合成普通渠道原话"]

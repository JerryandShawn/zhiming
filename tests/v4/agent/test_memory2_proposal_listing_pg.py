"""Pending proposals from idle reflection are listed for the owner and disappear once withdrawn."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app
from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_withdrawals import MemoryWithdrawalService

from .test_memory2_reflection_real_pg import LIKE, idle, item, reflect, say
from .test_memory2_reflection_real_pg import life as life  # noqa: F401  (pytest fixture)

HEADERS = {"X-Token": "synthetic-proposal-token"}


def client(repo: Any, monkeypatch) -> TestClient:
    monkeypatch.setenv("MINGJING_TOKEN", HEADERS["X-Token"])
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.delenv("ZHIMING_TOKEN_OWNERS", raising=False)
    return TestClient(create_app(service=SimpleNamespace(repo=repo)))


def test_inferred_proposal_is_listed_with_own_quote_then_removed_with_source(life, monkeypatch):  # noqa: F811
    repo, clock, thread = life
    source = say(repo, clock, LIKE + "，周末常去山里。")
    idle(clock)
    assert reflect(repo, clock, thread, [item(source, "周末常去山里", explicit=False)])[0] == "completed"
    web = client(repo, monkeypatch)
    listed = web.get("/api/memory2/proposals", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    [row] = listed.json()
    assert row["status"] == "pending" and row["inferred"] is True and row["quotes"] == ["周末常去山里"]
    assert row["confirmable"] is False and row["needs_confirmation_reason"] == "inferred_or_event"
    assert not {"source_ids", "source_refs", "fact_metadata"} & set(row)
    assert web.get("/api/memory2/proposals", params={"subject_id": "nobody"}, headers=HEADERS).status_code == 404
    command = say(repo, clock, "删除这条来源消息")
    MemoryWithdrawalService(V4FactMemory(repo)).delete_source(
        "alice",
        "self",
        source["id"],
        expected_revision=source["revision"],
        message_id=command["id"],
        operation_id="delete-listed-original",
    )
    assert web.get("/api/memory2/proposals", headers=HEADERS).json() == []

"""Confirm/ignore/undo for non-sensitive idle-reflection proposals through the authenticated web routes."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app
from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_reflection_model import ScriptedFactModel
from mingjing_core.application.memory2_reflection_real import RealMemoryReflection
from mingjing_core.application.memory2_withdrawals import MemoryWithdrawalService
from mingjing_core.application.threads import ThreadService
from mingjing_core.timekit.clock import FrozenClock

from .test_toolkit_pg import SAID_AT

HEADERS = {"X-Token": "synthetic-memory-web"}
TEXT = "我喜欢合成徒步，周末常去山里。"
GUESS = "周末常去山里"


@pytest.fixture
def web(p2_repo, monkeypatch):
    clock = FrozenClock(SAID_AT)
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", clock)
    monkeypatch.setenv("MINGJING_TOKEN", HEADERS["X-Token"])
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", json.dumps({"synthetic-bob": "bob"}))
    core = SimpleNamespace(repo=p2_repo, memory=V4FactMemory(p2_repo))
    return p2_repo, clock, TestClient(create_app(core))


def reflected(repo, clock, items):
    thread = ThreadService(repo, clock=clock).create("alice", request_id="life")
    clock.advance(timedelta(seconds=1))
    source = V4FactMemory(repo).receive("alice", content=TEXT, source_id=uuid.uuid4().hex, at=clock.now())
    clock.advance(timedelta(minutes=10))
    model = ScriptedFactModel([dict(row, message_id=source["id"]) for row in items])
    assert RealMemoryReflection(repo, clock, model=model).thread("alice", thread["id"], "self") == "completed"
    clock.advance(timedelta(minutes=1))
    return source


def guess(kind="preference"):
    return {"quote": GUESS, "kind": kind, "explicit": False, "summary": "可能偏好户外"}


def post(client, ident, action, key, revision=1, headers=HEADERS, **values):
    return client.post(
        f"/api/memory2/proposals/{ident}/{action}",
        headers=headers,
        json={"request_id": key, "expected_revision": revision, **values},
    )


def listed(client, headers=HEADERS):
    response = client.get("/api/memory2/proposals", headers=headers)
    assert response.status_code == 200
    return response.json()["items"]


def test_inferred_proposal_is_listed_confirmed_and_undone(web):
    repo, clock, client = web
    source = reflected(repo, clock, [guess()])
    [row] = listed(client)
    assert row["quote"] == GUESS and row["inferred"] is True and row["sensitive"] is False
    assert row["can_remember_category"] is False and row["message_id"] == source["id"]
    response = post(client, row["id"], "confirm", "confirm-guess", row["revision"])
    assert response.status_code == 200, response.text
    fact = next(f for f in repo.list("alice", "fact") if f["content"] == GUESS)
    assert fact["status"] == "active" and fact["source_refs"][0]["message_id"] == source["id"]
    assert len(fact["source_refs"]) == 2 and fact["source_refs"][1]["quote"] == "请保存这条记忆"
    accepted = repo.get("alice", "proposal", row["id"])
    assert accepted["status"] == "accepted" and listed(client) == []
    assert post(client, row["id"], "confirm", "confirm-guess", row["revision"]).json() == response.json()
    undone = post(client, row["id"], "undo", "undo-guess", accepted["revision"])
    assert undone.status_code == 200, undone.text
    assert repo.get("alice", "fact", fact["id"], include_deleted=True)["status"] == "retired"
    assert [item["id"] for item in listed(client)] == [row["id"]]


def test_ignore_removes_and_remember_category_is_refused(web):
    repo, clock, client = web
    reflected(repo, clock, [guess()])
    [row] = listed(client)
    before = repo.get_revision("alice")
    refused = post(client, row["id"], "confirm", "remember-guess", row["revision"], remember_category=True)
    assert refused.status_code >= 400
    assert repo.get("alice", "proposal", row["id"])["status"] == "pending"
    assert all(f["content"] != GUESS for f in repo.list("alice", "fact"))
    settings = repo.assert_scope("alice", "self")["settings"]
    assert "auto_save_categories" not in settings and repo.get_revision("alice") >= before
    ignored = post(client, row["id"], "ignore", "ignore-guess", row["revision"])
    assert ignored.status_code == 200, ignored.text
    assert repo.get("alice", "proposal", row["id"], include_deleted=True)["status"] == "deleted"
    assert listed(client) == []


def test_cross_owner_cannot_list_or_act(web):
    repo, clock, client = web
    reflected(repo, clock, [guess()])
    [row] = listed(client)
    bob = {"X-Token": "synthetic-bob"}
    assert listed(client, bob) == []
    before = repo.get_revision("alice")
    assert post(client, row["id"], "confirm", "bob-confirm", row["revision"], headers=bob).status_code == 404
    assert post(client, row["id"], "ignore", "bob-ignore", row["revision"], headers=bob).status_code == 404
    assert repo.get_revision("alice") == before and repo.list("bob", "message") == []


def test_unauthenticated_list_is_rejected(web):
    _, _, client = web
    assert client.get("/api/memory2/proposals").status_code in {401, 403}


def test_other_normal_proposals_still_cannot_be_confirmed(web):
    repo, clock, client = web
    source = reflected(repo, clock, [guess()])
    [row] = listed(client)
    plain = dict(repo.get("alice", "proposal", row["id"]))
    for key in ("id", "revision", "status", "subject_id", "case_id", "created_at", "updated_at", "owner", "kind_"):
        plain.pop(key, None)
    plain.update(status="pending", origin="agent")
    repo.put("alice", "proposal", "proposal_plain_normal", plain, expected_revision=0)
    response = post(client, "proposal_plain_normal", "confirm", "plain-confirm", 1)
    assert response.status_code >= 400
    assert all(f["content"] != GUESS for f in repo.list("alice", "fact")) and source["id"]


def test_confirmed_reflection_fact_follows_original_deletion(web):
    repo, clock, client = web
    source = reflected(repo, clock, [guess()])
    [row] = listed(client)
    assert post(client, row["id"], "confirm", "confirm-then-delete", row["revision"]).status_code == 200
    fact = next(f for f in repo.list("alice", "fact") if f["content"] == GUESS)
    memory = V4FactMemory(repo)
    command = memory.receive("alice", content="删除这条来源消息", source_id="delete-command", at=clock.now())
    MemoryWithdrawalService(memory).delete_source(
        "alice",
        "self",
        source["id"],
        expected_revision=source["revision"],
        message_id=command["id"],
        operation_id="delete-confirmed-original",
    )
    assert repo.get("alice", "fact", fact["id"], include_deleted=True)["status"] == "deleted"
    assert repo.is_revoked("alice", "fact", fact["id"])
    assert listed(client) == []


def test_event_confirmation_uses_existing_date_verification(web):
    repo, clock, client = web
    undated = {"quote": "我喜欢合成徒步", "kind": "event", "explicit": False, "summary": "合成事件"}
    reflected(repo, clock, [guess("event"), undated])
    rows = {row["quote"]: row for row in listed(client)}
    assert {row["kind"] for row in rows.values()} == {"event"}
    refused = post(
        client, rows["我喜欢合成徒步"]["id"], "confirm", "confirm-undated", rows["我喜欢合成徒步"]["revision"]
    )
    assert refused.status_code >= 400
    assert repo.get("alice", "proposal", rows["我喜欢合成徒步"]["id"])["status"] == "pending"
    dated = post(client, rows[GUESS]["id"], "confirm", "confirm-dated", rows[GUESS]["revision"])
    assert dated.status_code == 200, dated.text
    fact = next(f for f in repo.list("alice", "fact") if f["content"] == GUESS)
    assert fact["kind"] == "event" and fact["event_at"]

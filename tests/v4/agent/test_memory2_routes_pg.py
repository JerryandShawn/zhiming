"""Authenticated ASGI clicks exercise native proposals, exact undo and replay guards."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app
from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.timekit.clock import FrozenClock

from .test_memory2_profile_proposals_pg import candidate
from .test_memory2_proposals_pg import pending
from .test_memory2_slots_pg import pair, update
from .test_memory2_conflicts_pg import conflict
from .test_toolkit_pg import SAID_AT

HEADERS = {"X-Token": "synthetic-memory-web"}


@pytest.fixture
def web(p2_repo, monkeypatch):
    monkeypatch.setenv("MINGJING_TOKEN", HEADERS["X-Token"])
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", json.dumps({"synthetic-bob": "bob"}))
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", FrozenClock(SAID_AT + timedelta(days=7)))
    core = SimpleNamespace(repo=p2_repo, memory=V4FactMemory(p2_repo))
    return p2_repo, TestClient(create_app(core))


def post(client, ident, action, key, revision=1, **values):
    return client.post(
        f"/api/memory2/proposals/{ident}/{action}",
        headers=HEADERS,
        json={"request_id": key, "expected_revision": revision, **values},
    )


@pytest.mark.parametrize("remember", [False, True])
def test_native_sensitive_confirmation_click_and_replay(web, remember):
    repo, client = web
    h, ident = pending(repo)
    first = post(client, ident, "confirm", "confirm", remember_category=remember)
    assert first.status_code == 200, first.text
    fact = repo.get("alice", "fact", first.json()["fact_id"])
    assert len(fact["source_refs"]) == 2
    assert repo.get("alice", "message", fact["source_refs"][-1]["message_id"])["channel"] == "web-action"
    version = repo.get_revision("alice")
    replay = post(client, ident, "confirm", "confirm", remember_category=remember)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert repo.get_revision("alice") == version
    assert "诊断" not in first.text and "source_refs" not in first.text
    settings = repo.assert_scope("alice")["settings"].get("auto_save_categories", [])
    assert ("health" in settings) is remember
    h.finish()


def test_ignore_and_slot_undo_are_real_replayable_service_actions(web):
    repo, client = web
    h, ident = pending(repo)
    first = post(client, ident, "ignore", "ignore")
    assert first.status_code == 200
    assert post(client, ident, "ignore", "ignore").json() == first.json()
    h.finish()
    old, new = pair(repo)
    receipt = update(repo, old, new)
    change = receipt["ids"][0]
    payload = {"request_id": "undo-slot", "expected_revision": 1, "change_type": "slot"}
    response = client.post(f"/api/memory2/changes/{change}/undo", headers=HEADERS, json=payload)
    assert response.status_code == 200, response.text
    assert repo.get("alice", "fact", old["id"])["content"] == old["content"]
    assert repo.get("alice", "fact", new["id"])["status"] == "retired"
    version = repo.get_revision("alice")
    assert client.post(f"/api/memory2/changes/{change}/undo", headers=HEADERS, json=payload).json() == response.json()
    assert repo.get_revision("alice") == version


@pytest.mark.parametrize("mode", ["unauthenticated", "owner", "subject", "revision", "bool_revision", "extra"])
def test_bad_identity_or_shape_cannot_create_action_sources(web, mode):
    repo, client = web
    h, ident = pending(repo)
    payload = {"request_id": "invalid", "expected_revision": 1}
    headers = HEADERS
    if mode == "unauthenticated":
        headers = {}
    elif mode == "owner":
        headers = {"X-Token": "synthetic-bob"}
    elif mode == "subject":
        repo.create_subject("alice", "other", "合成其他人物")
        payload["subject_id"] = "other"
    elif mode == "revision":
        payload["expected_revision"] = 99
    elif mode == "bool_revision":
        payload["expected_revision"] = True
    else:
        payload["owner"] = "bob"
    before = repo.get_revision("alice")
    response = client.post(f"/api/memory2/proposals/{ident}/confirm", headers=headers, json=payload)
    assert response.status_code in {401, 404, 409, 422}
    assert repo.get_revision("alice") == before and repo.list("alice", "fact") == []
    h.finish()


def test_profile_native_proposals_use_profile_service_not_fact_confirmation(web):
    repo, client = web
    proposal, _ = candidate(repo)
    first = post(client, proposal["id"], "confirm", "profile")
    assert first.status_code == 200, first.text
    item = repo.get("alice", "profile_doc", first.json()["id"])
    assert item["confirmed_by_user"] is True
    assert post(client, proposal["id"], "confirm", "profile").json() == first.json()
    current = repo.get("alice", "proposal", proposal["id"])
    undone = post(client, proposal["id"], "undo", "undo-profile", current["revision"])
    assert undone.status_code == 200, undone.text
    assert repo.get("alice", "profile_doc", item["id"], include_deleted=True)["status"] == "deleted"
    assert post(client, proposal["id"], "undo", "undo-profile", current["revision"]).json() == undone.json()


@pytest.mark.parametrize("path", ["confirm", "ignore", "undo", "change"])
def test_every_route_rejects_cross_owner_before_action_source_write(web, path):
    repo, client = web
    h, ident = pending(repo)
    payload = {"request_id": "cross-owner", "expected_revision": 1}
    url = f"/api/memory2/proposals/{ident}/{path}"
    if path == "change":
        payload["change_type"] = "slot"
        url = f"/api/memory2/changes/{ident}/undo"
    before = repo.get_revision("alice")
    response = client.post(url, headers={"X-Token": "synthetic-bob"}, json=payload)
    assert response.status_code == 404
    assert repo.get_revision("alice") == before and repo.list("bob", "message") == []
    h.finish()


def test_reused_request_key_cannot_authorize_another_action_and_revoked_source_cannot_replay(web):
    repo, client = web
    h, ident = pending(repo)
    first = post(client, ident, "confirm", "stable")
    assert first.status_code == 200
    before = repo.get_revision("alice")
    refused = post(client, ident, "ignore", "stable")
    assert refused.status_code in {409, 422} and repo.get_revision("alice") == before
    fact = repo.get("alice", "fact", first.json()["fact_id"])
    V4FactMemory(repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    before = repo.get_revision("alice")
    assert post(client, ident, "confirm", "stable").status_code in {409, 422}
    assert repo.get_revision("alice") == before
    assert repo.get("alice", "fact", first.json()["fact_id"], include_deleted=True)["status"] == "deleted"
    assert repo.get_run("alice", h.run["id"])["status"] == "revoked"


def test_profile_ignore_replays_even_after_private_proposal_body_is_scrubbed(web):
    repo, client = web
    proposal, _ = candidate(repo)
    first = post(client, proposal["id"], "ignore", "ignore-profile")
    assert first.status_code == 200
    before = repo.get_revision("alice")
    replay = post(client, proposal["id"], "ignore", "ignore-profile")
    assert replay.status_code == 200 and replay.json() == first.json()
    assert repo.get_revision("alice") == before


@pytest.mark.parametrize("choice", ["old", "new"])
def test_conflict_requires_explicit_choice_and_uses_native_resolution_and_undo(web, choice):
    repo, client = web
    _, old, pending, _, _ = conflict(repo)
    ident = pending.receipt["id"]
    before = repo.get_revision("alice")
    assert post(client, ident, "confirm", "missing-choice").status_code == 422
    assert repo.get_revision("alice") == before
    chosen = post(client, ident, "confirm", "choose", choice=choice)
    assert chosen.status_code == 200, chosen.text
    before = repo.get_revision("alice")
    assert post(client, ident, "confirm", "choose", choice=choice).json() == chosen.json()
    assert repo.get_revision("alice") == before
    proposal = repo.get("alice", "proposal", ident)
    assert proposal["status"] == "resolved_" + choice
    undone = post(client, ident, "undo", "undo-choice", revision=proposal["revision"])
    assert undone.status_code == 200, undone.text
    assert repo.get("alice", "proposal", ident)["status"] == "pending"
    assert repo.get("alice", "fact", old["id"])["status"] == "active"
    before = repo.get_revision("alice")
    assert post(client, ident, "undo", "undo-choice", revision=proposal["revision"]).json() == undone.json()
    assert repo.get_revision("alice") == before

"""Real authenticated profile edits keep original facts and exact replay boundaries."""

import pytest

from mingjing_core.application.agent_tools_policy import V4FactMemory

from .test_memory2_profile_proposals_pg import candidate
from .test_memory2_routes_pg import HEADERS, post
from .test_memory2_routes_pg import web as native_web


@pytest.fixture(name="web")
def profile_web(p2_repo, monkeypatch):
    return native_web.__wrapped__(p2_repo, monkeypatch)


def accepted(repo, client):
    proposal, fact = candidate(repo)
    response = post(client, proposal["id"], "confirm", "accept-profile")
    assert response.status_code == 200, response.text
    return repo.get("alice", "profile_doc", response.json()["id"]), fact


def change(client, item, action, *, key="edit-profile", headers=HEADERS, **values):
    return client.post(
        f"/api/memory2/profile/{item['id']}/{action}",
        headers=headers,
        json={"request_id": key, "expected_revision": item["revision"], **values},
    )


def test_view_edit_delete_and_replays_preserve_original_fact(web):
    repo, client = web
    item, fact = accepted(repo, client)
    url = f"/api/memory2/profile/{item['id']}"
    view = client.get(url, headers=HEADERS)
    assert view.status_code == 200 and set(view.json()) == {"id", "revision", "section", "text", "confirmed_by_user"}
    edited = change(client, item, "edit", text="我想把画像描述改得更简洁")
    assert edited.status_code == 200, edited.text
    current = repo.get("alice", "profile_doc", item["id"])
    assert current["edited_by_user"] is True and current["fact_versions"] == item["fact_versions"]
    assert repo.get("alice", "fact", fact["id"]) == fact
    before = repo.get_revision("alice")
    assert change(client, item, "edit", text="我想把画像描述改得更简洁").json() == edited.json()
    assert repo.get_revision("alice") == before
    removed = change(client, current, "delete", key="delete-profile")
    assert removed.status_code == 200 and removed.json()["write_status"] == "deleted"
    before = repo.get_revision("alice")
    assert change(client, current, "delete", key="delete-profile").json() == removed.json()
    assert repo.get_revision("alice") == before and repo.get("alice", "fact", fact["id"]) == fact
    assert client.get(url, headers=HEADERS).status_code in {404, 422}
    assert change(client, item, "edit", text="我想把画像描述改得更简洁").status_code == 409


@pytest.mark.parametrize("action", ["view", "edit", "delete"])
def test_each_profile_route_has_owner_authentication_before_writes(web, action):
    repo, client = web
    item, _ = accepted(repo, client)
    before = repo.get_revision("alice")
    if action == "view":
        response = client.get(f"/api/memory2/profile/{item['id']}", headers={"X-Token": "synthetic-bob"})
    else:
        response = change(
            client, item, action, headers={"X-Token": "synthetic-bob"}, **({"text": "合成"} if action == "edit" else {})
        )
    assert response.status_code == 404
    assert repo.get_revision("alice") == before and repo.list("bob", "message") == []


@pytest.mark.parametrize(
    "values",
    [
        {"expected_revision": True},
        {"expected_revision": 99},
        {"subject_id": "other"},
        {"text": " "},
        {"text": "API_KEY=synthetic-secret"},
        {"section": 7},
    ],
)
def test_invalid_edits_create_no_authorization_or_fact(web, values):
    repo, client = web
    item, _ = accepted(repo, client)
    repo.create_subject("alice", "other", "合成人物")
    before = repo.get_revision("alice")
    response = change(client, item, "edit", **dict({"text": "合成编辑"}, **values))
    assert response.status_code in {404, 409, 422}, response.text
    assert repo.get_revision("alice") == before


def test_reused_key_or_withdrawn_original_cannot_replay_edit(web):
    repo, client = web
    item, fact = accepted(repo, client)
    first = change(client, item, "edit", text="合成用户编辑")
    assert first.status_code == 200, first.text
    before = repo.get_revision("alice")
    assert change(client, item, "edit", text="另一条编辑").status_code in {409, 422}
    assert repo.get_revision("alice") == before
    V4FactMemory(repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    before = repo.get_revision("alice")
    assert change(client, item, "edit", text="合成用户编辑").status_code in {409, 422}
    assert repo.get_revision("alice") == before

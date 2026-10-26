"""Real leased calculation failure, native web discovery and explicit profile save."""

from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from mingjing_core.adapters.web import create_app
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.p8_profile_confirmation import profile_confirmation_cards

from . import test_p8_agent_charts_pg as chart_tests
from .test_p8_agent_charts_pg import registered


@pytest.fixture(name="repo")
def repository(p2_repo, monkeypatch):
    return chart_tests.repository.__wrapped__(p2_repo, monkeypatch)


def failed_chart(repo):
    h, args, ctx, step = registered(repo, metadata=False)
    result = h.registry.execute("chart_compute", args, ctx)
    assert not result.ok and result.data == {
        "code": "MISSING_INPUT",
        "required_fields": ["birth.location.tz", "birth.clock_basis"],
        "next_action": "profile_confirmation",
    }
    return h, step, result


def test_only_native_completed_step_offers_readonly_card_without_birth_values(repo):
    h, step, result = failed_chart(repo)
    service = SimpleNamespace(repo=repo, memory=MemoryService(repo))
    revision = repo.get_revision("alice")
    assert profile_confirmation_cards(service, "alice", "default") == []
    h.journal.complete(step, result.model_dump())
    cards = profile_confirmation_cards(service, "alice", "default")
    assert len(cards) == 1 and cards[0]["action"] == "open_profile"
    assert cards[0]["required_fields"] == result.data["required_fields"]
    assert "2012" not in str(cards) and "104.07" not in str(cards)
    assert profile_confirmation_cards(service, "alice", "other-conversation") == []
    assert repo.get_revision("alice") == revision
    assert repo.list("alice", "artifact") == repo.list("alice", "proposal") == []
    h.finish()
    assert profile_confirmation_cards(service, "alice", "default") == []


def test_native_http_card_opens_existing_confirmation_route_explicitly_and_then_disappears(p2_repo, monkeypatch):
    repo = p2_repo  # The native in-process ASGI transport is the HTTP under test.
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-token")
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", '{"synthetic-bob":"bob"}')
    h, step, result = failed_chart(repo)
    h.journal.complete(step, result.model_dump())
    client = TestClient(create_app(SimpleNamespace(repo=repo, memory=MemoryService(repo))))
    headers = {"X-Token": "synthetic-token"}
    url = "/api/subjects/self/profile/requirements?conversation_id=default"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"X-Token": "synthetic-bob"}).json() == []
    assert client.get(url, headers=headers).json()[0]["required_fields"] == result.data["required_fields"]
    snapshot = client.get("/api/subjects/self/profile", headers=headers).json()
    payload = {
        "request_id": "explicit-p8-profile",
        "expected_revision": snapshot["revision"],
        "profile": {"birth": {"location": {"tz": "Asia/Shanghai"}, "clock_basis": "clock"}},
    }
    save = "/api/subjects/self/profile/confirm"
    assert client.post(save, headers=headers, json=payload | {"confirmed": False}).status_code == 422
    assert "birth.location.tz" not in MemoryService(repo).snapshot("alice")["profile"]
    response = client.post(save, headers=headers, json=payload | {"confirmed": True})
    assert response.status_code == 200 and len(response.json()["receipts"]) == 2
    assert client.post(save, headers=headers, json=payload | {"confirmed": True}).json() == response.json()
    assert client.get(url, headers=headers).json() == []
    assert repo.list("alice", "artifact") == []  # No calculation or automatic retry on save.
    h.finish()


@pytest.mark.parametrize("mode", ["source_changed", "source_deleted", "source_revision", "incognito", "old_epoch"])
def test_stale_private_or_withdrawn_native_requirement_cannot_return_card(repo, mode):
    from psycopg import sql

    h, step, result = failed_chart(repo)
    h.journal.complete(step, result.model_dump())
    if mode in {"source_changed", "source_deleted", "source_revision"}:
        source = repo.get("alice", "message", h.source["id"])
        if mode == "source_revision":
            from psycopg.types.json import Jsonb

            with repo.transaction("alice") as connection:
                connection.execute(
                    sql.SQL("UPDATE {} SET state_version=%s WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
                    (Jsonb({"message:" + source["id"]: source["revision"]}), "alice", h.run["id"]),
                )
        changes = {"content": "已改动的合成来源"} if mode == "source_changed" else {"status": "deleted"}
        if mode == "source_revision":
            changes = {"content": source["content"]}  # Equal text does not restore the old version.
        repo.update(
            "alice",
            "message",
            source["id"],
            changes,
            expected_revision=source["revision"],
            operation_id="test-stale-source",
        )
    else:
        with repo.transaction("alice") as connection:
            change = "thread_id='incognito:self'" if mode == "incognito" else "retry_epoch=retry_epoch+1"
            connection.execute(
                sql.SQL("UPDATE {} SET " + change + " WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
                ("alice", h.run["id"]),
            )
    assert profile_confirmation_cards(SimpleNamespace(repo=repo, memory=MemoryService(repo)), "alice", "default") == []
    if mode != "old_epoch":
        h.finish()

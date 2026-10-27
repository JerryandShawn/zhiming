"""Authenticated HTTP threads and lifespan workers execute only injected scripts."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app
from mingjing_core.agent.events import validate_event
from mingjing_core.application.read_result import read_result
from mingjing_core.repositories.postgres import PostgresRepository

from .test_dispatcher_pg import until
from .test_loop_cycle_support import ScriptedPort, answer
from .test_runtime_assembly_pg import configure, service
from .test_runtime_assembly_pg import repository_fixture as source_repo_fixture
from tests.v4.streaming_integration.legacy_event_support import flat_frames

HEADERS = {"X-Token": "synthetic-http-owner"}


@pytest.fixture(name="http_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    monkeypatch.setenv("MINGJING_TOKEN", HEADERS["X-Token"])
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", json.dumps({"synthetic-bob": "bob"}))
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def decoded(response: Any) -> list[dict]:
    result = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            result.append({"type": lines["event"], "data": json.loads(lines["data"])})
    return result


def test_thread_api_lifespan_dispatches_core4_and_replays_frozen_sse(http_repo: PostgresRepository) -> None:
    repo, port = http_repo, ScriptedPort([answer("合成HTTP闭环")])
    configure(repo)
    core = service(repo, port)
    with TestClient(create_app(core)) as client:
        thread = client.post("/api/threads", headers=HEADERS, json={"request_id": "life"}).json()
        response = client.post(
            f"/api/threads/{thread['id']}/messages",
            headers=HEADERS,
            json={"request_id": "question", "message": "合成HTTP问题"},
        )
        assert response.status_code == 202
        queued = response.json()
        until(lambda: repo.fetch_run("alice", queued["run_id"])["status"] == "succeeded")
        response = client.get(queued["events_url"], headers=HEADERS)
        events = decoded(response)
        assert response.status_code == 200 and events[-1]["type"] == "final"
        assert events[-1]["data"]["envelope"]["text"] == "合成HTTP闭环"
        for event in events:
            validate_event(event["type"], event["data"])
        last = events[-2]["data"]["seq"]
        replay = decoded(client.get(queued["events_url"], headers=dict(HEADERS, **{"Last-Event-ID": str(last)})))
        assert [event["data"]["seq"] for event in replay] == [events[-1]["data"]["seq"]]
        assert "合成受控推理" not in response.text and "lease_token" not in response.text
        history = client.get(f"/api/threads/{thread['id']}/messages", headers=HEADERS).json()
        assert [row["role"] for row in history["items"]] == ["user", "assistant"]
        assert len(port.requests) == 1 and core.runtime_assembly.legacy.calls == []


def test_private_close_scrubs_history_and_events_and_is_idempotent(http_repo: PostgresRepository) -> None:
    configure(http_repo)
    core = service(http_repo, ScriptedPort([answer("合成私密答复")]))
    with TestClient(create_app(core)) as client:
        response = client.post("/api/threads", headers=HEADERS, json={"request_id": "private", "incognito": True})
        thread = response.json()["id"]
        run = client.post(
            f"/api/threads/{thread}/messages",
            headers=HEADERS,
            json={"request_id": "private-message", "message": "合成私密原话"},
        ).json()
        until(lambda: http_repo.fetch_run("alice", run["run_id"])["status"] == "succeeded")
        first = client.post(f"/api/threads/{thread}/close", headers=HEADERS, json={"request_id": "close-private"})
        again = client.post(f"/api/threads/{thread}/close", headers=HEADERS, json={"request_id": "close-private"})
        assert first.status_code == again.status_code == 200 and first.json() == again.json()
        assert client.get(f"/api/threads/{thread}/messages", headers=HEADERS).status_code == 422
        events = client.get(run["events_url"], headers=HEADERS)
        assert "合成私密原话" not in events.text and "合成私密答复" not in events.text
        assert decoded(events)[-1]["data"]["code"] == "SOURCE_REVOKED"


def test_client_runtime_fields_and_cross_owner_reads_are_rejected(http_repo: PostgresRepository) -> None:
    configure(http_repo)
    core = service(http_repo, ScriptedPort([]))
    client = TestClient(create_app(core))
    thread = client.post("/api/threads", headers=HEADERS, json={"request_id": "life"}).json()["id"]
    denied = client.post(
        f"/api/threads/{thread}/messages",
        headers=HEADERS,
        json={"request_id": "invalid", "message": "不应出现在错误里的原话", "runtime": "v3"},
    )
    assert denied.status_code == 422 and "不应出现在错误里的原话" not in denied.text
    assert http_repo.list("alice", "message") == []
    assert client.get(f"/api/threads/{thread}/messages", headers={"X-Token": "synthetic-bob"}).status_code == 403


def test_missing_agent_does_not_start_dispatcher_or_fall_back(http_repo: PostgresRepository) -> None:
    configure(http_repo)
    core = service(http_repo)
    with TestClient(create_app(core)) as client:
        response = client.post("/api/threads", headers=HEADERS, json={"request_id": "missing-agent"})
        assert response.status_code == 422 and core.runtime_assembly.legacy.calls == []
        assert http_repo.list("alice", "message") == []


def test_compat_chat_opted_in_v4_uses_legacy_events_and_rejects_private_hint(http_repo: PostgresRepository) -> None:
    configure(http_repo)
    core = service(http_repo, ScriptedPort([answer("合成兼容入口")]))
    with TestClient(create_app(core)) as client:
        rejected = client.post(
            "/api/chat",
            headers=HEADERS,
            json={"request_id": "private-hint", "message": "不应落入人生线程", "incognito": True},
        )
        assert rejected.status_code == 422 and http_repo.list("alice", "message") == []
        result = client.post("/api/chat", headers=HEADERS, json={"request_id": "compat-v4", "message": "合成兼容问题"})
        assert result.status_code == 200
        frames = flat_frames(result.text)
        run = http_repo.fetch_run("alice", frames[0]["run_id"])
        final = next(frame for frame in frames if frame["type"] == "result")
        assert final["result"] == read_result(run["result"]) and run["result"]["text"] == "合成兼容入口"
        assert run["result"]["schema_version"] == "core4.0" and len(core.runtime_assembly.agent.port.requests) == 1
        assert core.runtime_assembly.legacy.calls == [] and len(http_repo.list("alice", "message")) == 2


def test_json_chat_ack_then_frozen_get_preserves_same_core4(http_repo: PostgresRepository) -> None:
    configure(http_repo)
    core = service(http_repo, ScriptedPort([answer("合成JSON与冻结流")]))
    payload = {"request_id": "json-compat-v4", "message": "合成JSON问题"}
    with TestClient(create_app(core)) as client:
        response = client.post("/api/chat", headers=dict(HEADERS, Accept="application/json"), json=payload)
        ack = response.json()
        assert response.status_code == 202
        until(lambda: http_repo.fetch_run("alice", ack["run_id"])["status"] == "succeeded")
        run = http_repo.fetch_run("alice", ack["run_id"])
        events = decoded(client.get(ack["events_url"], headers=HEADERS))
        assert ack["message_id"] == run["request"]["source_message_id"]
        assert events[-1]["type"] == "final" and events[-1]["data"]["envelope"] == run["result"]
        for event in events:
            validate_event(event["type"], event["data"])
        assert len(core.runtime_assembly.agent.port.requests) == 1 and core.runtime_assembly.legacy.calls == []


def test_v4_cancel_route_does_not_clear_live_lease_before_worker_stops(http_repo: PostgresRepository) -> None:
    configure(http_repo)
    core = service(http_repo, ScriptedPort([]))
    run = core.submit(owner="alice", request_id="cancel-queued", message="合成停止请求")
    claimed = http_repo.claim_run("alice", run["id"])
    client = TestClient(create_app(core))
    response = client.post(f"/api/runs/{run['id']}/cancel", headers=HEADERS)
    current = http_repo.fetch_run("alice", run["id"])
    assert response.status_code == 200 and current["cancel_requested_at"] is not None
    assert current["status"] == "running" and current["lease_token"] == claimed["lease_token"]

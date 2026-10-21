"""JSON returns committed identities before the real dispatcher finishes a script."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mingjing_core.adapters.web import create_app
from mingjing_core.application.run_acceptance import run_acceptance
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from tests.v4.agent.legacy_dom_http_support import local_app
from tests.v4.agent.test_loop_cycle_support import ScriptedPort, answer
from tests.v4.agent.test_runtime_assembly_pg import configure, service
from tests.v4.streaming_integration.chat_acceptance_support import WaitingPort, counts
from tests.v4.streaming_integration.chat_acceptance_support import (
    repository as repository,
)
from tests.v4.streaming_integration.event_http_support import HEADERS, decoded, until

JSON = dict(HEADERS, Accept="application/json")


def test_json_ack_precedes_model_completion_and_get_replays_same_run(
    acceptance_repo: Any,
) -> None:
    repo, port = acceptance_repo, WaitingPort()
    configure(repo)
    core = service(repo, port)
    with (
        local_app(create_app(core)) as base,
        httpx.Client(base_url=base, trust_env=False, timeout=10) as client,
    ):
        try:
            response = client.post(
                "/api/chat",
                headers=JSON,
                json={"request_id": "async-json", "message": "合成异步问题"},
            )
            assert response.status_code == 202 and response.headers["vary"] == "Accept"
            assert response.headers["cache-control"] == "no-store"
            ack = response.json()
            assert ack["runtime"] == "v4" and ack["status"] == "queued"
            assert port.started.wait(3) and port.requests == []
            assert_committed_source(core, ack, "合成异步问题")
            assert repo.fetch_run("alice", ack["run_id"])["result"] is None
            port.release.set()
            until(
                lambda: repo.fetch_run("alice", ack["run_id"])["status"] == "succeeded"
            )
            events = decoded(client.get(ack["events_url"], headers=HEADERS).text)
            assert (
                events[-1]["type"] == "final"
                and events[-1]["data"]["envelope"]["text"] == "合成异步答复"
            )
            replay = client.post(
                "/api/chat",
                headers=JSON,
                json={"request_id": "async-json", "message": "合成异步问题"},
            )
            assert replay.json() == dict(ack, status="succeeded")
            legacy_request = client.post(
                "/api/chat",
                headers=dict(HEADERS, Accept="text/event-stream"),
                json={"request_id": "async-json", "message": "合成异步问题"},
            )
            assert decoded(legacy_request.text)[-1] == events[-1]
            assert len(port.requests) == 1 and len(repo.list("alice", "message")) == 2
            assert core.runtime_assembly.legacy.calls == []
        finally:
            port.release.set()


@pytest.mark.parametrize(
    "accept",
    [
        "application/json",
        "text/plain",
        "application/json;q=secret",
        "text/event-stream;q=0,*/*",
    ],
)
def test_v3_or_invalid_accept_rejects_before_any_database_or_media_write(
    acceptance_repo: Any, monkeypatch: Any, tmp_path: Any, accept: str
) -> None:
    repo = acceptance_repo
    monkeypatch.setenv("ZHIMING_MEDIA_PATH", str(tmp_path / "must-not-exist"))
    core = service(repo, ScriptedPort([]))
    with (
        local_app(create_app(core)) as base,
        httpx.Client(base_url=base, trust_env=False) as client,
    ):
        before = counts(repo)
        response = client.post(
            "/api/chat",
            headers=dict(HEADERS, Accept=accept),
            json={
                "request_id": "denied",
                "message": "不应入库的合成内容",
                "images": ["not-an-image"],
            },
        )
        assert response.status_code == 406 and counts(repo) == before
        assert not (tmp_path / "must-not-exist").exists()
        assert "secret" not in response.text and "不应入库" not in response.text
        assert core.runtime_assembly.legacy.calls == []


def test_json_unknown_owner_does_not_create_identity(
    acceptance_repo: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("MINGJING_OWNER_ID", "uncreated-synthetic-owner")
    with local_app(create_app(service(acceptance_repo, ScriptedPort([])))) as base:
        with httpx.Client(base_url=base, trust_env=False) as client:
            before = counts(acceptance_repo)
            response = client.post(
                "/api/chat",
                headers=JSON,
                json={"request_id": "no-owner", "message": "合成"},
            )
            assert response.status_code == 406 and counts(acceptance_repo) == before


@pytest.mark.parametrize("unavailable", ["agent", "meter", "capacity"])
def test_json_missing_agent_or_dispatcher_does_not_store_source(
    acceptance_repo: Any,
    unavailable: str,
) -> None:
    configure(acceptance_repo)
    core = service(
        acceptance_repo, None if unavailable == "agent" else ScriptedPort([])
    )
    if unavailable == "meter":
        core.runtime_assembly.agent.meter = None
    if unavailable == "capacity":
        acceptance_repo.max_running = 1
    with (
        local_app(create_app(core)) as base,
        httpx.Client(base_url=base, trust_env=False) as client,
    ):
        before = counts(acceptance_repo)
        response = client.post(
            "/api/chat",
            headers=JSON,
            json={"request_id": "not-started", "message": "合成"},
        )
        assert response.status_code == 422 and counts(acceptance_repo) == before


def test_ack_uses_real_private_thread_and_thread_api_source(
    acceptance_repo: Any,
) -> None:
    repo = acceptance_repo
    configure(repo)
    core = service(repo, ScriptedPort([answer("合成私密答复"), answer("合成线程答复")]))
    with (
        local_app(create_app(core)) as base,
        httpx.Client(base_url=base, trust_env=False, timeout=10) as client,
    ):
        ack = client.post(
            "/api/chat",
            headers=JSON,
            json={"request_id": "private-json", "message": "开个无痕，合成临时问题"},
        ).json()
        assert ack["thread_id"].startswith("incognito:")
        assert (
            core.memory.get_source("alice", ack["message_id"])["thread_id"]
            == ack["thread_id"]
        )
        until(lambda: repo.fetch_run("alice", ack["run_id"])["status"] == "succeeded")
        configure(repo, "v3")
        replay = client.post(
            "/api/chat",
            headers=JSON,
            json={"request_id": "private-json", "message": "开个无痕，合成临时问题"},
        )
        assert replay.status_code == 202 and replay.json() == dict(
            ack, status="succeeded"
        )
        configure(repo)
        thread = client.post(
            "/api/threads", headers=HEADERS, json={"request_id": "life"}
        ).json()["id"]
        ack = client.post(
            f"/api/threads/{thread}/messages",
            headers=HEADERS,
            json={"request_id": "thread-source", "message": "合成线程原话"},
        ).json()
        assert (
            repo.fetch_run("alice", ack["run_id"])["request"]["source_message_id"]
            == ack["message_id"]
        )


def test_inbox_ack_is_child_identity_not_parent_and_source_ack_cannot_cross_owner(
    acceptance_repo: Any,
) -> None:
    repo = acceptance_repo
    configure(repo)
    core = service(repo, ScriptedPort([]))
    parent = core.submit(owner="alice", request_id="parent", message="合成主轮")
    lease = repo.claim_run("alice", parent["id"])
    child = core.submit(owner="alice", request_id="child", message="合成补充")
    ack = run_acceptance(repo, "alice", child["id"])
    assert (
        ack["run_id"] == child["id"] != parent["id"] and ack["status"] == "inbox_wait"
    )
    assert ack["message_id"] != parent["request"]["source_message_id"]
    with pytest.raises(ScopeError):
        run_acceptance(repo, "bob", child["id"])
    repo.fail_run(
        "alice", parent["id"], "component-fixture-completed", lease["lease_token"]
    )
    original = core.memory.get_source("alice", ack["message_id"])
    repo.update(
        "alice",
        "message",
        original["id"],
        {"content": "更改后的合成内容"},
        expected_revision=original["revision"],
    )
    with pytest.raises(EvidenceError):
        run_acceptance(repo, "alice", child["id"])


def assert_committed_source(core: Any, ack: dict, text: str) -> None:
    assert set(ack) == {
        "run_id",
        "message_id",
        "thread_id",
        "status",
        "runtime",
        "events_url",
        "run_url",
    }
    actual = core.repo.fetch_run("alice", ack["run_id"])
    source = core.memory.get_source("alice", ack["message_id"])
    assert ack["message_id"] == actual["request"]["source_message_id"] == source["id"]
    assert ack["thread_id"] == actual["thread_id"] == source["thread_id"]
    assert source["content"] == text


def test_authentication_precedes_malformed_accept(acceptance_repo: Any) -> None:
    with local_app(create_app(service(acceptance_repo, ScriptedPort([])))) as base:
        with httpx.Client(base_url=base, trust_env=False) as client:
            before = counts(acceptance_repo)
            response = client.post(
                "/api/chat",
                headers={"X-Token": "wrong", "Accept": "invalid;q=secret"},
                json={"request_id": "auth-first", "message": "合成"},
            )
            assert response.status_code == 401 and counts(acceptance_repo) == before


def test_v3_json_with_sse_fallback_keeps_real_legacy_protocol_and_runtime(
    acceptance_repo: Any,
) -> None:
    from mingjing_core.application.consultation import ConsultationService
    from tests.test_core_pg_channels import FixtureModel

    model = FixtureModel()
    core = ConsultationService(acceptance_repo, model=model)
    with (
        local_app(create_app(core)) as base,
        httpx.Client(base_url=base, trust_env=False, timeout=10) as client,
    ):
        response = client.post(
            "/api/chat",
            headers=dict(HEADERS, Accept="application/json,text/event-stream"),
            json={"request_id": "old-fallback", "message": "合成旧协议问题"},
        )
        assert response.status_code == 200 and response.headers[
            "content-type"
        ].startswith("text/event-stream")
        assert '"type": "result"' in response.text and "[DONE]" in response.text
        assert len(model.requests) == 2 and "event: final" not in response.text
        with acceptance_repo.transaction("alice") as connection:
            from psycopg import sql

            row = connection.execute(
                sql.SQL(
                    "SELECT runtime FROM {} WHERE owner='alice' AND operation_id='old-fallback'"
                ).format(acceptance_repo.table("core_runs"))
            ).fetchone()
        assert (
            row["runtime"] == "v3"
            and "runtime" not in acceptance_repo.assert_scope("alice")["settings"]
        )


def test_running_inbox_socket_ack_returns_its_own_message_and_waiting_run(
    acceptance_repo: Any,
) -> None:
    repo, port = acceptance_repo, WaitingPort()
    configure(repo)
    core = service(repo, port)
    with (
        local_app(create_app(core)) as base,
        httpx.Client(base_url=base, trust_env=False, timeout=10) as client,
    ):
        try:
            parent = core.submit(
                owner="alice", request_id="inbox-parent", message="合成主轮问题"
            )
            assert port.started.wait(3)
            response = client.post(
                "/api/chat",
                headers=JSON,
                json={"request_id": "inbox-child", "message": "合成运行中补充"},
            )
            ack = response.json()
            assert response.status_code == 202 and ack["status"] == "inbox_wait"
            assert (
                ack["run_id"] != parent["id"]
                and ack["message_id"] != parent["request"]["source_message_id"]
            )
            assert_committed_source(core, ack, "合成运行中补充")
            assert ack["events_url"] == "/api/runs/" + ack["run_id"] + "/events"
        finally:
            if "parent" in locals():
                client.post("/api/runs/" + parent["id"] + "/cancel", headers=HEADERS)
            # A finite provider fixture can complete both parent and any recovered child.
            port.responses.extend([answer("合成后续答复")])
            port.release.set()

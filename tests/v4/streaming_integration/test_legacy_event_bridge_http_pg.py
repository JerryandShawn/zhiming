"""Actual sockets consume old POST and frozen GET from one real PG execution."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mingjing_core.adapters.web import create_app
from mingjing_core.agent.events import validate_event
from mingjing_core.application.read_result import read_result
from tests.v4.agent.legacy_dom_http_support import local_app
from tests.v4.agent.test_loop_cycle_support import ScriptedPort, answer
from tests.v4.agent.test_runtime_assembly_pg import configure, service
from tests.v4.streaming_integration.chat_acceptance_support import WaitingPort
from tests.v4.streaming_integration.event_http_support import HEADERS, decoded, until
from tests.v4.streaming_integration.legacy_event_support import flat_frames
from tests.v4.streaming_integration.legacy_event_support import repository as repository


@pytest.mark.parametrize("hints", [False, True])
def test_default_legacy_post_json_ack_and_frozen_get_share_one_canonical_result(
    legacy_repo: Any, hints: bool
) -> None:
    repo, port = legacy_repo, ScriptedPort([answer("合成同源终稿")])
    configure(repo)
    core, payload = (
        service(repo, port),
        {"request_id": "legacy-one", "message": "合成同源问题"},
    )
    app = create_app(core, event_hints=hints)
    with (
        local_app(app) as base,
        httpx.Client(base_url=base, trust_env=False, timeout=10) as client,
    ):
        response = client.post("/api/chat", headers=HEADERS, json=payload)
        assert response.status_code == 200 and "event: final" not in response.text
        assert response.text.count("data: [DONE]") == 1
        frames = flat_frames(response.text)
        started, result = (
            frames[0],
            next(frame for frame in frames if frame["type"] == "result"),
        )
        assert started["type"] == "started" and frames[1]["type"] == "context"
        run = repo.fetch_run("alice", started["run_id"])
        assert result["result"] == read_result(run["result"])
        assert (
            run["result"]["schema_version"] == "core4.0"
            and "memory_receipts" not in run["result"]
        )
        ack = client.post(
            "/api/chat", headers=dict(HEADERS, Accept="application/json"), json=payload
        ).json()
        assert ack["run_id"] == run["id"] and ack["message_id"] == started["message_id"]
        events = decoded(client.get(ack["events_url"], headers=HEADERS).text)
        assert (
            events[-1]["type"] == "final"
            and events[-1]["data"]["envelope"] == run["result"]
        )
        for event in events:
            validate_event(event["type"], event["data"])
        assert len(port.requests) == 1 and core.runtime_assembly.legacy.calls == []
        assert len(repo.list("alice", "message")) == 2
        if hints:
            until(
                lambda: app.state.core["event_hints"].statistics()["subscriptions"] == 0
            )


def test_slow_model_old_post_emits_started_before_final_and_disconnect_releases_hint(
    legacy_repo: Any,
) -> None:
    repo, port = legacy_repo, WaitingPort()
    configure(repo)
    core = service(repo, port)
    app = create_app(core, event_hints=True)
    with (
        local_app(app) as base,
        httpx.Client(base_url=base, trust_env=False, timeout=10) as client,
    ):
        try:
            with client.stream(
                "POST",
                "/api/chat",
                headers=HEADERS,
                json={"request_id": "slow-old", "message": "合成慢速问题"},
            ) as response:
                assert response.status_code == 200
                lines = response.iter_lines()
                while (line := next(lines)) == "" or not line.startswith("data:"):
                    continue
                started = flat_frames(line)[0]
                assert (
                    started["type"] == "started"
                    and port.started.wait(3)
                    and port.requests == []
                )
            until(
                lambda: app.state.core["event_hints"].statistics()["subscriptions"] == 0
            )
            port.release.set()
            until(
                lambda: repo.fetch_run("alice", started["run_id"])["status"]
                == "succeeded"
            )
            assert len(port.requests) == 1
        finally:
            port.release.set()


def test_actual_cancel_ends_old_stream_with_current_persistent_error(
    legacy_repo: Any,
) -> None:
    repo, port = legacy_repo, WaitingPort()
    configure(repo)
    core = service(repo, port)
    with (
        local_app(create_app(core, event_hints=True)) as base,
        httpx.Client(base_url=base, trust_env=False, timeout=10) as client,
    ):
        try:
            with client.stream(
                "POST",
                "/api/chat",
                headers=HEADERS,
                json={"request_id": "cancel-old", "message": "合成停止问题"},
            ) as response:
                lines = response.iter_lines()
                while (line := next(lines)) == "" or not line.startswith("data:"):
                    continue
                started = flat_frames(line)[0]
                assert started["type"] == "started" and port.started.wait(3)
                assert (
                    client.post(
                        "/api/runs/" + started["run_id"] + "/cancel", headers=HEADERS
                    ).status_code
                    == 200
                )
                port.release.set()
                rest = "\n".join(lines)
            frames = flat_frames(rest)
            assert [frame["type"] for frame in frames].count("error") == 1
            assert "result" not in [frame["type"] for frame in frames]
            assert (
                next(frame for frame in frames if frame["type"] == "error")["code"]
                == "RUN_CANCELLED"
            )
            assert rest.count("data: [DONE]") == 1
        finally:
            port.release.set()

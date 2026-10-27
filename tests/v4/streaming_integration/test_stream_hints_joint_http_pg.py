"""The actual Runtime timer and installed hints share real PG and socket HTTP."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from mingjing_core.adapters.web import create_app
from mingjing_core.application.run_event_hub import Subscription
from mingjing_core.application.run_event_stream_worker import StreamWorker
from mingjing_core.timekit.clock import SystemClock, get_clock, set_clock
from tests.v4.agent.legacy_dom_http_support import local_app
from tests.v4.agent.test_dispatcher_http import quiet_server
from tests.v4.streaming_integration.event_http_support import HEADERS, frame, until
from tests.v4.streaming_integration.stream_joint_http_support import (
    JointPort,
    child_phase,
    child_runtime,
    direct_clients,
    event_rows,
    joint_service,
    post_turn,
)
from tests.v4.streaming_integration.test_event_listener_pg import listeners


@pytest.fixture
def joint(
    p2_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Any, list[StreamWorker], threading.Event, dict[str, bool]]]:
    direct_clients(monkeypatch)
    workers, entered = [], threading.Event()
    start, wait = StreamWorker.start, Subscription.wait
    options = {"strict_notification": True}

    def capture(worker: StreamWorker) -> None:
        workers.append(worker)
        start(worker)

    async def notification_only(self: Subscription, timeout: float) -> Any:
        entered.set()
        return await wait(self, 5 if options["strict_notification"] else timeout)

    monkeypatch.setattr(StreamWorker, "start", capture)
    monkeypatch.setattr(Subscription, "wait", notification_only)
    previous = get_clock()
    set_clock(SystemClock())
    try:
        yield p2_repo, workers, entered, options
    finally:
        set_clock(previous)


def through(lines: Any, *, delta: bool = False) -> list[dict[str, Any]]:
    result = []
    for _ in range(60):
        value = frame(lines)
        result.append(value)
        if delta and value["type"] == "text_delta" or not delta and value["type"] in {"final", "error"}:
            return result
    raise AssertionError("bounded synthetic event sequence did not reach its expected boundary")


def assert_quiet_delta(repo: Any, ident: str, values: list[dict[str, Any]], end: threading.Event) -> None:
    value = values[-1]
    assert value["type"] == "text_delta" and 0 < len(value["data"]["text"]) < 40
    assert not end.is_set()
    actual = next(row for row in event_rows(repo, ident) if row["seq"] == value["data"]["seq"])
    assert actual["kind"] == "text_delta" and actual["payload"] == value["data"]


def test_joint_flags_deliver_timer_delta_through_real_http_notification(joint: Any) -> None:
    repo, workers, entered, _ = joint
    with quiet_server() as (base, started, end):
        port = JointPort(base, entered)
        app = create_app(joint_service(repo, port), event_hints=True)
        with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
            until(lambda: app.state.core["event_hints"].statistics()["listener_ready"])
            ident = post_turn(client, origin, HEADERS)
            with client.stream("GET", origin + f"/api/runs/{ident}/events", headers=HEADERS) as response:
                assert response.status_code == 200
                lines = response.iter_lines()
                prefix = through(lines, delta=True)
                assert started.is_set() and entered.is_set()
                assert_quiet_delta(repo, ident, prefix, end)
                assert app.state.core["event_hints"].statistics()["notifications"] >= 1
                end.set()
                values = prefix + through(lines)
                assert values[-1]["type"] == "final"
                assert values[-1]["data"]["envelope"]["schema_version"] == "core4.0"
            until(lambda: app.state.core["event_hints"].statistics()["subscriptions"] == 0)
            assert port.request_count == 1 and workers and workers[0].done.wait(1)
    assert listeners(repo) == []


def test_joint_child_runtime_commit_reconnects_without_duplicate_seq(joint: Any) -> None:
    repo, _, entered, _ = joint
    with quiet_server() as (base, started, end):
        creator = joint_service(repo, JointPort(base))
        run = creator.submit(owner="alice", request_id="joint-child", message="合成跨进程真实模型循环")
        app = create_app(joint_service(repo), event_hints=True)
        with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
            until(lambda: app.state.core["event_hints"].statistics()["listener_ready"])
            endpoint = origin + f"/api/runs/{run['id']}/events"
            with client.stream("GET", endpoint, headers=HEADERS) as first:
                assert first.status_code == 200 and entered.wait(1)
                with child_runtime(repo, run["id"], base) as process:
                    assert started.wait(5), "isolated child startup phase: " + child_phase(process)
                    try:
                        prefix = through(first.iter_lines(), delta=True)
                    except httpx.ReadTimeout:
                        current = repo.fetch_run("alice", run["id"])
                        raise AssertionError(
                            json.dumps(
                                {
                                    "child": child_phase(process),
                                    "status": current["status"],
                                    "stream": current["usage"].get("p4_stream_candidate"),
                                }
                            )
                        ) from None
                    assert started.is_set()
                    assert_quiet_delta(repo, run["id"], prefix, end)
                    first.close()
                    cursor = prefix[-1]["data"]["seq"]
                    with client.stream(
                        "GET", endpoint, headers=dict(HEADERS, **{"Last-Event-ID": str(cursor)})
                    ) as second:
                        assert second.status_code == 200
                        end.set()
                        tail = through(second.iter_lines())
                    output, errors = process.communicate(timeout=5)
                    assert process.returncode == 0 and not errors, "isolated Runtime process must succeed safely"
                    assert json.loads(output) == {"succeeded": True, "physical_requests": 1}
            values = prefix + tail
            actual = event_rows(repo, run["id"])
            assert [event["data"]["seq"] for event in values] == [row["seq"] for row in actual]
            assert len({event["data"]["seq"] for event in values}) == len(values)
            assert values[-1]["type"] == "final"
            until(lambda: app.state.core["event_hints"].statistics()["subscriptions"] == 0)
    assert listeners(repo) == []


def test_joint_http_cancel_stops_quiet_socket_actor_and_late_publication(joint: Any) -> None:
    repo, workers, entered, options = joint
    # Cancellation uses the actual 150ms fallback; only delta probes suppress it.
    options["strict_notification"] = False
    with quiet_server() as (base, _, end):
        port = JointPort(base, entered)
        app = create_app(joint_service(repo, port), event_hints=True)
        with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
            until(lambda: app.state.core["event_hints"].statistics()["listener_ready"])
            ident = post_turn(client, origin, HEADERS)
            with client.stream("GET", origin + f"/api/runs/{ident}/events", headers=HEADERS) as response:
                lines = response.iter_lines()
                prefix = through(lines, delta=True)
                assert_quiet_delta(repo, ident, prefix, end)
                stamp = time.monotonic()
                stopped = client.post(origin + f"/api/runs/{ident}/cancel", headers=HEADERS)
                assert stopped.status_code == 200
                until(lambda: repo.fetch_run("alice", ident)["status"] == "cancelled", timeout=2)
                tail = through(lines)
                assert time.monotonic() - stamp < 2
                assert tail[-1]["type"] == "error" and not any(event["type"] == "final" for event in prefix + tail)
            assert port.closed.wait(1) and workers and workers[0].done.wait(1)
            assert not workers[0].thread.is_alive() and repo.fetch_run("alice", ident)["result"] is None
            until(lambda: repo.pool.get_stats()["pool_available"] == repo.pool.get_stats()["pool_size"])
            before = event_rows(repo, ident)
            end.set()
            time.sleep(0.2)
            assert event_rows(repo, ident) == before and port.request_count == 1
            assert repo.pool.get_stats()["requests_waiting"] == 0
            until(lambda: app.state.core["event_hints"].statistics()["subscriptions"] == 0)
    assert listeners(repo) == []

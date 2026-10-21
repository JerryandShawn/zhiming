"""Real socket lifecycle, a terminated own listener and source/cancel fences."""

from __future__ import annotations

import threading

import httpx
import pytest

from mingjing_core.adapters.web import create_app
from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.run_event_listener import EventListener
from mingjing_core.domain.contracts import CoreError
from tests.v4.agent.legacy_dom_http_support import local_app
from tests.v4.agent.test_runtime_assembly_pg import service
from tests.v4.streaming_integration.event_http_support import (
    HEADERS,
    decoded,
    frame,
    isolate,
    until,
)
from tests.v4.streaming_integration.test_event_listener_pg import listeners
from tests.v4.streaming_integration.test_event_notify_pg import claimed, started


@pytest.fixture
def http_repo(p2_repo, monkeypatch):
    isolate(monkeypatch)
    return p2_repo


def test_http_reads_real_pg_while_its_actual_terminated_listener_waits_to_reconnect(
    http_repo, monkeypatch
):
    repo, run = http_repo, claimed(http_repo)
    retry, blocked, calls = threading.Event(), threading.Event(), []
    original = EventListener._connected

    def controlled_retry(self):
        calls.append(True)
        if len(calls) > 1:
            blocked.set()
            assert retry.wait(5), "bounded synthetic reconnect pause expired"
        return original(self)

    monkeypatch.setattr(EventListener, "_connected", controlled_retry)
    app = create_app(service(repo), event_hints=True)
    try:
        with (
            local_app(app) as origin,
            httpx.Client(timeout=2, trust_env=False) as client,
        ):
            hints = app.state.core["event_hints"]
            until(lambda: hints.statistics()["listener_ready"])
            with client.stream(
                "GET", origin + f"/api/runs/{run['id']}/events", headers=HEADERS
            ) as response:
                assert response.status_code == 200
                previous = listeners(repo)
                assert len(previous) == 1
                with repo.transaction() as connection:
                    assert connection.execute(
                        "SELECT pg_terminate_backend(%s) AS ok", (previous[0],)
                    ).fetchone()["ok"]
                assert blocked.wait(2)
                assert not hints.statistics()["listener_ready"]
                RuntimeEvents(repo, run, None).send("started", started(run))
                actual = frame(response.iter_lines())
                assert actual["type"] == "started" and actual["data"]["seq"] == 1
                assert hints.statistics()["notifications"] == 0
                retry.set()
                until(lambda: hints.statistics()["listener_ready"])
                assert len(listeners(repo)) == 1 and listeners(repo) != previous
            until(lambda: hints.statistics()["subscriptions"] == 0)
    finally:
        retry.set()
    assert listeners(repo) == []


def test_two_actual_app_event_loops_share_one_connection_and_release_independently(
    http_repo,
):
    repo, run = http_repo, claimed(http_repo)
    first, second = (
        create_app(service(repo), event_hints=True),
        create_app(service(repo), event_hints=True),
    )
    with local_app(first) as one, httpx.Client(timeout=2, trust_env=False) as client:
        first_hints = first.state.core["event_hints"]
        until(lambda: first_hints.statistics()["listener_ready"])
        with local_app(second) as two:
            second_hints = second.state.core["event_hints"]
            assert (
                len(listeners(repo)) == 1 and second_hints.statistics()["scopes"] == 2
            )
            path = f"/api/runs/{run['id']}/events"
            with (
                client.stream("GET", one + path, headers=HEADERS) as left,
                client.stream("GET", two + path, headers=HEADERS) as right,
            ):
                assert left.status_code == right.status_code == 200
                until(lambda: first_hints.statistics()["subscriptions"] == 2)
                RuntimeEvents(repo, run, None).send("started", started(run))
                assert frame(left.iter_lines()) == frame(right.iter_lines())
            until(lambda: first_hints.statistics()["subscriptions"] == 0)
        assert first_hints.statistics()["scopes"] == 1 and len(listeners(repo)) == 1
    assert listeners(repo) == []


@pytest.mark.parametrize("change", ["revoke", "cancel"])
def test_real_http_uses_actual_terminal_and_never_reconstructs_cleared_originals(
    http_repo, change
):
    repo, run = http_repo, claimed(http_repo)
    events = RuntimeEvents(repo, run, None)
    events.send("started", started(run))
    events.send("text_delta", {"text": "合成已撤销片段不能复活"})
    if change == "revoke":
        repo.invalidate_derived("alice", [], [run["request"]["source_message_id"]])
    else:
        cancellation = DispatcherCancellation(repo)
        cancellation.request("alice", run["id"])
        cancellation.finish(run)
    with pytest.raises(CoreError):
        events.send("text_delta", {"text": "合成迟到结果不得发布"})
    app = create_app(service(repo), event_hints=True)
    with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
        response = client.get(origin + f"/api/runs/{run['id']}/events", headers=HEADERS)
        actual = decoded(response.text)
        assert response.status_code == 200 and actual[-1]["type"] == "error"
        expected = "SOURCE_REVOKED" if change == "revoke" else "RUN_CANCELLED"
        assert actual[-1]["data"]["code"] == expected
        assert "合成迟到结果不得发布" not in response.text
        if change == "revoke":
            assert "合成已撤销片段不能复活" not in response.text
            assert len(actual) == 1 and actual[0]["data"]["seq"] == 3
        until(lambda: app.state.core["event_hints"].statistics()["subscriptions"] == 0)
    assert listeners(repo) == []

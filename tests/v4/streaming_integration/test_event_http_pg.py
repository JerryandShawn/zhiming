"""Socket HTTP + disposable PG exercise the installed hint consumer, never an ASGI fake."""

from __future__ import annotations

import threading

import httpx
import pytest

from mingjing_core.adapters.web import create_app
from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.run_event_hub import Subscription
from tests.v4.agent.legacy_dom_http_support import local_app
from tests.v4.agent.test_runtime_assembly_pg import service
from tests.v4.streaming_integration.event_http_support import (
    HEADERS,
    decoded,
    frame,
    isolate,
    producer,
    until,
)
from tests.v4.streaming_integration.test_event_listener_pg import listeners
from tests.v4.streaming_integration.test_event_notify_pg import claimed, started


@pytest.fixture
def http_repo(p2_repo, monkeypatch):
    isolate(monkeypatch)
    return p2_repo


def test_real_http_is_woken_by_fresh_process_commit_not_the_fallback_poll(
    http_repo, monkeypatch
):
    repo, run, entered = http_repo, claimed(http_repo), threading.Event()
    waits = []
    original = Subscription.wait

    async def notification_only(self, timeout):
        waits.append(self.ident)
        entered.set()
        return await original(self, 5)

    # Only lengthen the trusted fallback wait; actual LISTEN, queue, PG reader and socket remain real.
    monkeypatch.setattr(Subscription, "wait", notification_only)
    app = create_app(service(repo), event_hints=True)
    with local_app(app) as origin, httpx.Client(timeout=2, trust_env=False) as client:
        hints = app.state.core["event_hints"]
        until(lambda: hints.statistics()["listener_ready"])
        with client.stream(
            "GET", origin + f"/api/runs/{run['id']}/events", headers=HEADERS
        ) as response:
            assert response.status_code == 200 and entered.wait(2)
            assert (
                hints.statistics()["subscriptions"] == 1 and len(listeners(repo)) == 1
            )
            with repo.transaction() as connection:
                connection.execute(
                    "SELECT pg_notify('mj_run',%s)",
                    (run["id"] + ":9223372036854775807",),
                )
                connection.execute("SELECT pg_notify('mj_run','unknown-run:7')")
            until(lambda: len(waits) >= 2)
            assert hints.statistics()["runs"] == 1
            actual = producer(repo, run)
            frames = response.iter_lines()
            first, second = frame(frames), frame(frames)
            assert actual == {
                "seqs": [1, 2],
                "producer": "actual-leased-runtime-events",
            }
            assert [first["type"], second["type"]] == ["started", "text_delta"]
            assert second["data"]["text"] == "合成跨进程片段"
            assert [first["data"]["seq"], second["data"]["seq"]] == [1, 2]
            assert hints.statistics()["notifications"] >= 1
        until(lambda: hints.statistics()["subscriptions"] == 0)
        current = repo.fetch_run("alice", run["id"])
        assert current["status"] == "running" and current["cancel_requested_at"] is None
    assert listeners(repo) == []


def test_real_http_replays_over_one_thousand_rows_and_reconnects_at_actual_cursor(
    http_repo,
):
    repo, run = http_repo, claimed(http_repo)
    events = RuntimeEvents(repo, run, None)
    with repo.transaction("alice"):
        events.send("started", started(run))
        for index in range(1003):
            events.send("text_delta", {"text": "合成片段" + str(index)})
    repo.fail_run("alice", run["id"], "合成终态", run["lease_token"])
    app = create_app(service(repo), event_hints=True)
    with local_app(app) as origin, httpx.Client(timeout=5, trust_env=False) as client:
        response = client.get(origin + f"/api/runs/{run['id']}/events", headers=HEADERS)
        actual = decoded(response.text)
        assert response.status_code == 200 and len(actual) == 1005
        assert [event["data"]["seq"] for event in actual] == list(range(1, 1006))
        assert (
            actual[-1]["type"] == "error" and actual[-1]["data"]["code"] == "RUN_FAILED"
        )
        resumed = client.get(
            origin + f"/api/runs/{run['id']}/events",
            headers=dict(HEADERS, **{"Last-Event-ID": "999"}),
        )
        assert [event["data"]["seq"] for event in decoded(resumed.text)] == list(
            range(1000, 1006)
        )
        until(lambda: app.state.core["event_hints"].statistics()["subscriptions"] == 0)
    assert listeners(repo) == []


def test_real_http_auth_cursor_and_untrusted_hint_cannot_disclose_other_owner_or_jump_rows(
    http_repo,
):
    repo, run = http_repo, claimed(http_repo)
    RuntimeEvents(repo, run, None).send("started", started(run))
    repo.fail_run("alice", run["id"], "合成终态", run["lease_token"])
    app = create_app(service(repo), event_hints=True)
    with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
        endpoint = origin + f"/api/runs/{run['id']}/events"
        hints = app.state.core["event_hints"]
        denied = client.get(endpoint, headers={"X-Token": "synthetic-event-bob"})
        assert denied.status_code in {403, 422} and "合成流式原话" not in denied.text
        assert hints.statistics()["subscriptions"] == 0
        invalid = client.get(
            endpoint, headers=dict(HEADERS, **{"Last-Event-ID": "9000"})
        )
        assert invalid.status_code == 422 and hints.statistics()["subscriptions"] == 0
        with repo.transaction() as connection:
            connection.execute(
                "SELECT pg_notify('mj_run',%s)", (run["id"] + ":9223372036854775807",)
            )
        value = client.get(endpoint, headers=HEADERS)
        assert [event["data"]["seq"] for event in decoded(value.text)] == [1, 2]
        assert "lease_token" not in value.text


def test_candidate_default_has_zero_listener_and_http_cannot_enable_it(http_repo):
    repo = http_repo
    app = create_app(service(repo))
    with local_app(app) as origin, httpx.Client(timeout=3, trust_env=False) as client:
        assert app.state.core["event_hints"] is None and listeners(repo) == []
        assert (
            client.get(
                origin + "/api/threads?event_hints=true", headers=HEADERS
            ).status_code
            == 200
        )
        assert app.state.core["event_hints"] is None and listeners(repo) == []
    for value in (1, "true", None):
        with pytest.raises(ValueError, match="受信布尔"):
            create_app(service(repo), event_hints=value)

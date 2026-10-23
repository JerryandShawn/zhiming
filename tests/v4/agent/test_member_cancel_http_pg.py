"""A real quiet socket cancellation releases the real PG member permit in two seconds."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from models.test_quota_guard_pg import configure_central
from models.test_quota_http_pg import rows
from psycopg import sql

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher import AgentDispatcher
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.dispatcher_notifications import RunSignals
from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import PostgresRepository

from .member_wire_support import member_port, response
from .test_dispatcher_http import quiet_server
from .test_dispatcher_pg import queued, until
from .test_loop_cycle_support import SyntheticMeter


class LocalMember(OpenAICompat):
    offline = True


def test_quiet_http_cancel_releases_member_permit_and_keeps_interrupted_partial(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    guard = QuotaGuard(**configure_central(p2_repo, monkeypatch))
    repo, signals = p2_repo, RunSignals()
    run = queued(repo)
    with quiet_server() as (base, started, end):
        port = LocalMember(
            base_url=base,
            api_key="local-synthetic",
            model="k3-256k",
            provider="kimi_code",
            caps={"tools": True, "reasoning_replay": True},
            settings={"membership": True, "role_binding": "primary", "first_byte_timeout": 5, "total_timeout": 10},
            transport=httpx.HTTPTransport(retries=0),
            guard=guard,
            max_retries=0,
        )
        runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True, control_factory=signals.controls)
        worker = AgentDispatcher(SimpleNamespace(repo=repo, runtime=runtime), signals=signals)
        try:
            assert worker.tick() == 1 and started.wait(3)

            def fragment_saved() -> bool:
                with repo.transaction("alice") as connection:
                    return bool(
                        connection.execute(
                            sql.SQL("SELECT 1 FROM {} WHERE run_id=%s AND kind='text_delta'").format(
                                repo.table("core_run_events")
                            ),
                            (run["id"],),
                        ).fetchone()
                    )

            until(fragment_saved)
            assert guard.status()["in_flight"] == 1
            stamp = time.monotonic()
            DispatcherCancellation(repo, signals).request("alice", run["id"])
            until(lambda: repo.fetch_run("alice", run["id"])["status"] == "cancelled", timeout=2)
            assert time.monotonic() - stamp < 2 and not end.is_set()
            worker.active[run["id"]].result(timeout=2)
            assert port.request_count == 1 and guard.status()["in_flight"] == 0
            assert rows(guard)[0]["status"] == "cancelled" and rows(guard)[0]["run_id"] == run["id"]
            partial = [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]
            assert len(partial) == 1 and partial[0]["status"] == "interrupted"
            assert (
                partial[0]["content"] == "已经生成的合成片段" and repo.fetch_run("alice", run["id"])["result"] is None
            )
        finally:
            end.set()
            worker.close()


def test_non_cancelled_connection_error_keeps_unavailable_classification(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    guard = QuotaGuard(**configure_central(p2_repo, monkeypatch))

    def unavailable(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("SYNTHETIC_PRIVATE_DIAGNOSTIC")

    port = member_port(guard, unavailable)
    with pytest.raises(ModelUnavailable) as error:
        port.complete([])
    assert "SYNTHETIC_PRIVATE_DIAGNOSTIC" not in str(error.value)
    assert port.request_count == 1 and rows(guard)[0]["status"] == "unavailable"
    assert guard.status()["in_flight"] == 0


def test_fully_completed_stream_close_does_not_become_cancelled(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    guard = QuotaGuard(**configure_central(p2_repo, monkeypatch))
    cancel = threading.Event()
    port = member_port(guard, lambda _: response())
    stream = port.stream([], cancel_event=cancel)
    assert list(stream)[-1].type == "done"
    cancel.set()
    stream.close()
    assert port.request_count == 1 and len(rows(guard)) == 1 and rows(guard)[0]["status"] == "ok"
    assert guard.status()["in_flight"] == 0

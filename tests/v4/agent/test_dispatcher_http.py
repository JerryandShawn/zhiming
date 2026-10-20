"""Real loopback HTTP/SSE, isolated PG and scripted bytes; zero provider access."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.agent.loop_policy import LoopPolicy, RunControl
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher import AgentDispatcher
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.dispatcher_notifications import RunSignals
from mingjing_core.application.memory import MemoryService
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.repositories.postgres import PostgresRepository

from .test_dispatcher_pg import queued, until
from .test_loop_cycle_support import SyntheticMeter


@contextmanager
def quiet_server() -> Iterator[tuple[str, threading.Event, threading.Event]]:
    started, end = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            first = json.dumps({"choices": [{"delta": {"content": "已经生成的合成片段"}}]}, ensure_ascii=False)
            self.wfile.write(("data: " + first + "\n\n").encode())
            self.wfile.flush()
            started.set()
            # Deliberately no heartbeat or bytes: closing a quiet socket must
            # stop the blocked network read, not wait for a convenient fragment.
            end.wait(8)
            try:
                self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
                self.wfile.flush()
            except OSError:
                return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", started, end
    finally:
        end.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


@pytest.fixture(name="http_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    original = httpx.Client.send

    def only_loopback(self: httpx.Client, request: httpx.Request, *args: Any, **kwargs: Any) -> Any:
        assert request.url.host == "127.0.0.1" and request.url.scheme == "http"
        return original(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", only_loopback)
    for key in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    yield p2_repo


def verify_partial_replay_and_source_cleanup(repo: PostgresRepository, run: dict, claimed: dict, partial: dict) -> None:
    assert DispatcherCancellation(repo).finish(claimed)["status"] == "cancelled"
    assert len([row for row in repo.list("alice", "message") if row.get("role") == "assistant"]) == 1
    memory = MemoryService(repo)
    current_fact = memory.save_fact(
        "alice", "self", run["request"]["source_message_id"], run["request"]["message"], "preference"
    )
    memory.retire_fact("alice", current_fact["id"], expected_revision=current_fact["revision"], scope="source")
    redacted = repo.get("alice", "message", partial["id"], include_deleted=True)
    assert "已经生成的合成片段" not in redacted.get("content", "")


def test_real_quiet_http_cancel_closes_within_two_seconds_and_keeps_interrupted_partial(
    http_repo: PostgresRepository,
    record_property: Callable[[str, Any], None],
) -> None:
    class LocalScriptedHTTP(OpenAICompat):
        offline = True

    repo, signals = http_repo, RunSignals()
    run = queued(repo)
    with quiet_server() as (base, started, end):
        port = LocalScriptedHTTP(
            base_url=base,
            api_key="local-synthetic",
            model="scripted",
            provider="scripted",
            caps={"tools": True},
            transport=httpx.HTTPTransport(retries=0),
            max_retries=0,
            settings={"first_byte_timeout": 5, "total_timeout": 10},
        )
        runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True, control_factory=signals.controls)
        dispatcher = AgentDispatcher(SimpleNamespace(repo=repo, runtime=runtime), signals=signals)
        dispatcher.start()
        try:
            assert started.wait(3)
            until(lambda: bool(repo.fetch_run("alice", run["id"])["state_version"]))

            # Let the first real HTTP fragment reach the durable event sink.
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
            claimed = repo.fetch_run("alice", run["id"])
            stamp = time.monotonic()
            DispatcherCancellation(repo, signals).request("alice", run["id"])
            until(lambda: repo.fetch_run("alice", run["id"])["status"] == "cancelled", timeout=2)
            elapsed = time.monotonic() - stamp
            record_property("cancel_elapsed_seconds", elapsed)
            assert elapsed < 2
            partials = [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]
            assert len(partials) == 1 and partials[0]["status"] == "interrupted"
            assert partials[0]["content"] == "已经生成的合成片段"
            assert repo.fetch_run("alice", run["id"])["result"] is None and port.request_count == 1
            verify_partial_replay_and_source_cleanup(repo, run, claimed, partials[0])
        finally:
            end.set()
            dispatcher.close()


def test_real_pg_lease_is_renewed_by_twenty_second_stream_control(http_repo: PostgresRepository) -> None:
    repo, run = http_repo, queued(http_repo)
    run = repo.claim_run("alice", run["id"], lease_seconds=30)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET lease_until=now()+interval '10 second' WHERE id=%s").format(repo.table("core_runs")),
            (run["id"],),
        )
    elapsed = [0.0]
    control = RunControl(repo, run, LoopPolicy(), monotonic=lambda: elapsed[0])
    elapsed[0] = 21
    control.poll()
    with repo.transaction("alice") as connection:
        seconds = connection.execute(
            sql.SQL("SELECT extract(epoch FROM lease_until-now()) AS seconds FROM {} WHERE id=%s").format(
                repo.table("core_runs")
            ),
            (run["id"],),
        ).fetchone()["seconds"]
    assert 140 < seconds <= 150

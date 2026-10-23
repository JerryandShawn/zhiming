"""Measure cancellation across a real quiet loopback HTTP stream and PG15."""

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
from psycopg import sql

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher import AgentDispatcher
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.dispatcher_notifications import RunSignals
from mingjing_core.application.memory import MemoryService
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.repositories.postgres import PostgresRepository

from .v4_scripted import ScriptedMeter


@contextmanager
def quiet_server(partial: str) -> Iterator[tuple[str, threading.Event]]:
    end = threading.Event()

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
            first = json.dumps({"choices": [{"delta": {"content": partial}}]}, ensure_ascii=False)
            self.wfile.write(("data: " + first + "\n\n").encode())
            self.wfile.flush()
            end.wait(8)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", end
    finally:
        end.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def until(predicate: Callable[[], bool], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError("Local cancellation observation timed out")
        time.sleep(0.01)


def fragment_saved(repo: PostgresRepository, owner: str, ident: str) -> bool:
    with repo.transaction(owner) as connection:
        return bool(
            connection.execute(
                sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND run_id=%s AND kind='text_delta'").format(
                    repo.table("core_run_events")
                ),
                (owner, ident),
            ).fetchone()
        )


def queued(repo: PostgresRepository, owner: str) -> dict[str, Any]:
    source = MemoryService(repo).receive(owner, content="合成流式生成请求", source_id="v4-eval-cancel-source")
    run = repo.queue_run(
        owner, "v4-eval-cancel", {"message": source["content"], "source_message_id": source["id"], "case_ids": []}
    )
    with repo.transaction(owner) as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id='life:self' WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            (owner, run["id"]),
        )
    return repo.fetch_run(owner, run["id"])


def cancel_stream(repo: PostgresRepository, owner: str, *, partial: str, after_ms: int) -> dict[str, Any]:
    class LocalScriptedHTTP(OpenAICompat):
        offline = True

    if type(after_ms) is not int or not 0 <= after_ms <= 1000 or not partial or len(partial) > 2000:
        raise ValueError("Synthetic cancellation fixture is outside its bounded limits")
    run, signals = queued(repo, owner), RunSignals()
    with quiet_server(partial) as (base, end):
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
        runtime = AgentRuntime(repo, port, ScriptedMeter(), offline=True, control_factory=signals.controls)
        dispatcher = AgentDispatcher(SimpleNamespace(repo=repo, runtime=runtime), signals=signals)
        try:
            # A scenario's eval scope may use one bounded tick, never a permanent
            # dispatcher that would retain its temporary membership authority.
            if dispatcher.tick() != 1:
                raise ValueError("Synthetic cancellation must claim exactly its isolated run")
            until(lambda: fragment_saved(repo, owner, run["id"]), 5)
            time.sleep(after_ms / 1000)
            stamp = time.monotonic()
            requested = DispatcherCancellation(repo, signals).request(owner, run["id"])
            until(lambda: repo.fetch_run(owner, run["id"])["status"] == "cancelled", 2)
            elapsed = (time.monotonic() - stamp) * 1000
            current = repo.fetch_run(owner, run["id"])
            replies = [
                row for row in repo.list(owner, "message", include_deleted=True) if row.get("run_id") == run["id"]
            ]
            if not requested["cancel_requested_at"] or current["result"] is not None:
                raise ValueError("Cancellation did not leave authoritative stopped state")
            if len(replies) != 1 or replies[0]["status"] != "interrupted" or replies[0]["content"] != partial:
                raise ValueError("Cancelled stream partial is not the persisted fragment")
            return {
                "run_id": run["id"],
                "stop_latency_ms": elapsed,
                "scripted_http_requests": port.request_count,
                "partial_id": replies[0]["id"],
                "source_store": "core_runs.cancel_requested_at + core_run_events + core_entities",
                "rule": "monotonic request -> PG cancelled; quiet loopback socket, no external provider",
            }
        finally:
            end.set()
            dispatcher.close()

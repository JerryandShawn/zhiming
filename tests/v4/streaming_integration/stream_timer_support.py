"""Only provider transport is synthetic; Runtime, leases, ledger and events use PG."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.loop_policy import RunControl
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.port import ChatMessage, ModelPort, StreamEvent
from tools.eval.targets.v4_scripted import ScriptedMeter


class QuietPort(ModelPort):
    offline = True

    def __init__(self, *, fail_immediately: bool = False) -> None:
        self.quiet, self.release, self.cancelled = threading.Event(), threading.Event(), threading.Event()
        self.unavailable = threading.Event()
        self.calls, self.quiet_at = 0, 0.0
        self.fail_immediately = fail_immediately

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        self.calls += 1
        yield StreamEvent("text", "静默合成片")
        self.quiet_at = time.monotonic()
        self.quiet.set()
        if self.fail_immediately:
            raise ModelUnavailable()
        while not self.release.wait(0.005):
            if self.unavailable.is_set():
                raise ModelUnavailable()
            if kwargs["cancel_event"].is_set():
                self.cancelled.set()
                raise ModelUnavailable()
        yield StreamEvent("text", "结束")
        yield StreamEvent("usage", {})
        yield StreamEvent("done", {"provider": "scripted", "model": "synthetic-quiet"})


class BoundaryOnlyControl(RunControl):
    @contextmanager
    def monitor(self) -> Iterator[None]:
        # No periodic observer can hide a missing timer cancellation bridge.
        self.poll()
        yield
        self.poll()


class Legacy:
    def execute(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("a v4 timer must not route to legacy")

    def purge(self, *args: Any, **kwargs: Any) -> None:
        pass


def launch(repo: Any, port: QuietPort, *, message: str = "合成静默问题") -> tuple[dict, threading.Thread, dict]:
    runtime = AgentRuntime(
        repo, port, ScriptedMeter(), offline=True, streaming_candidate=True, control_factory=BoundaryOnlyControl
    )
    service = ConsultationService(
        repo, model=SimpleNamespace(model="synthetic"), runtime=Legacy(), agent_runtime=runtime
    )
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=settings||%s WHERE id='alice'").format(repo.table("core_owners")),
            (Jsonb({"runtime": "v4"}),),
        )
    run = service.submit(owner="alice", request_id=uuid.uuid4().hex, message=message)
    observed: dict[str, Any] = {}

    def execute() -> None:
        try:
            observed["result"] = service.execute("alice", run["id"])
        except BaseException as error:
            observed["error_type"] = type(error).__name__

    thread = threading.Thread(target=execute, daemon=True)
    thread.start()
    assert port.quiet.wait(1), "synthetic provider must reach its quiet phase"
    return run, thread, observed


def read_deltas(repo: Any, run: dict) -> list[str]:
    with repo.transaction() as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT payload FROM {} WHERE owner='alice' AND run_id=%s AND kind='text_delta' ORDER BY seq"
            ).format(repo.table("core_run_events")),
            (run["id"],),
        ).fetchall()
    return [row["payload"]["text"] for row in rows]

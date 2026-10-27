"""Only synthetic loopback HTTP is allowed in the joint candidate harness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.models.openai_compat import OpenAICompat
from tests.v4.agent.test_runtime_assembly_pg import LegacyRuntime
from tests.v4.streaming_integration.event_http_support import isolate
from tools.eval.targets.v4_scripted import ScriptedMeter


class JointPort(OpenAICompat):
    offline = True

    def __init__(self, base: str, gate: threading.Event | None = None) -> None:
        super().__init__(
            base_url=base,
            api_key="local-synthetic",
            model="scripted",
            provider="scripted",
            caps={"tools": True},
            transport=httpx.HTTPTransport(retries=0),
            max_retries=0,
            settings={"first_byte_timeout": 5, "total_timeout": 10},
        )
        self.gate, self.closed = gate, threading.Event()

    def stream(self, messages: Any, **kwargs: Any) -> Iterator[Any]:
        if self.gate is not None and not self.gate.wait(3):
            raise AssertionError("synthetic provider waits for the real SSE subscription")
        try:
            yield from super().stream(messages, **kwargs)
        finally:
            self.closed.set()


def direct_clients(monkeypatch: Any) -> None:
    isolate(monkeypatch)
    original = httpx.Client.__init__

    def direct(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["trust_env"] = False
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", direct)
    for name in tuple(os.environ):
        if name.upper().endswith("_PROXY"):
            monkeypatch.delenv(name, raising=False)


def joint_service(repo: Any, port: JointPort | None = None) -> ConsultationService:
    agent = AgentRuntime(repo, port, ScriptedMeter(), offline=True, streaming_candidate=True) if port else None
    service = ConsultationService(
        repo, model=SimpleNamespace(model="synthetic"), runtime=LegacyRuntime(), agent_runtime=agent
    )
    if agent is not None:
        agent.control_factory = service.runtime_assembly.signals.controls
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=settings||%s WHERE id='alice'").format(repo.table("core_owners")),
            (Jsonb({"runtime": "v4"}),),
        )
    return service


def event_rows(repo: Any, ident: str) -> list[dict[str, Any]]:
    with repo.transaction() as connection:
        return connection.execute(
            sql.SQL("SELECT seq,kind,payload FROM {} WHERE owner='alice' AND run_id=%s ORDER BY seq").format(
                repo.table("core_run_events")
            ),
            (ident,),
        ).fetchall()


def child_phase(process: subprocess.Popen[str]) -> str:
    if process.poll() is None:
        return "still_running"
    output, _ = process.communicate(timeout=1)
    try:
        value = json.loads(output)
        return json.dumps(value) if isinstance(value, dict) else "invalid_status"
    except ValueError:
        return "before_safe_status"


def post_turn(client: httpx.Client, origin: str, headers: dict) -> str:
    created = client.post(origin + "/api/threads", headers=headers, json={"request_id": "joint-thread"})
    assert created.status_code == 200
    response = client.post(
        origin + "/api/threads/life:self/messages",
        headers=headers,
        json={"request_id": "joint-turn", "message": "合成联合流式问题"},
    )
    assert response.status_code == 202
    return response.json()["run_id"]


@contextmanager
def child_runtime(repo: Any, ident: str, provider: str) -> Iterator[subprocess.Popen[str]]:
    root = Path(__file__).resolve().parents[3]
    helper = Path(__file__).with_name("stream_joint_process.py")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH") if key in os.environ}
    env.update(TZ="Asia/Tokyo", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", OTEL_SDK_DISABLED="true")
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2],run_name='__main__')"
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-X",
            "pycache_prefix=" + os.path.abspath(os.devnull),
            "-c",
            bootstrap,
            str(root),
            str(helper),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(json.dumps(dict(dsn=repo.dsn, schema=repo.schema, ident=ident, provider=provider)))
        process.stdin.close()
        process.stdin = None
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()

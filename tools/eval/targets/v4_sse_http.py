"""A quiet loopback listener serves the existing P3 event route unchanged."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import uvicorn
from fastapi import APIRouter, FastAPI, Request

from mingjing_core.adapters.thread_routes import event_routes
from mingjing_core.agent.events import validate_event
from mingjing_core.domain.contracts import ScopeError


@contextmanager
def event_listener(service: Any, owner: str) -> Iterator[str]:
    def auth(request: Request) -> str:
        if request.headers.get("X-Eval-Owner") != owner:
            raise ScopeError("离线事件请求不属于当前用户")
        return owner

    app, router = FastAPI(), APIRouter()
    event_routes(router, lambda _: service, auth)
    app.include_router(router)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", log_config=None, access_log=False, lifespan="off", ws="none")
    )
    worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started:
            if not worker.is_alive() or time.monotonic() >= deadline:
                raise TimeoutError("Offline P3 event listener did not start")
            time.sleep(0.01)
        yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        server.should_exit = True
        worker.join(timeout=5)
        listener.close()
        if worker.is_alive():
            raise TimeoutError("Offline P3 event listener did not stop")


def frames(response: Any, run_id: str) -> Iterator[dict[str, Any]]:
    if response.status_code != 200 or not response.headers.get("content-type", "").startswith("text/event-stream"):
        raise ValueError("Offline event endpoint did not return an SSE response")
    fields: dict[str, str] = {}
    for line in response.iter_lines():
        if line.startswith(":"):
            continue
        if not line:
            if fields:
                yield decode_frame(fields, run_id)
                fields = {}
            continue
        name, separator, value = line.partition(":")
        if not separator or name not in {"id", "event", "data"} or name in fields:
            raise ValueError("Offline SSE frame has unsupported or repeated fields")
        fields[name] = value.removeprefix(" ")
    if fields:
        raise ValueError("Offline SSE ended inside a frame")


def decode_frame(fields: dict[str, str], run_id: str) -> dict[str, Any]:
    if set(fields) != {"id", "event", "data"}:
        raise ValueError("Offline SSE frame is incomplete")
    value = validate_event(fields["event"], json.loads(fields["data"]))
    if fields["id"] != str(value["seq"]) or value["run_id"] != run_id:
        raise ValueError("Offline SSE native identity disagrees with its payload")
    return {"type": fields["event"], "data": value}

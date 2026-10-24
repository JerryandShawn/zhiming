"""Only the native dispatch and stdout flush are coordinated; OS exit and guards are real."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from contextlib import contextmanager
from typing import Any

from first_release_support import ROOT

BODY = "SYNTHETIC_SERVICE_BODY"
PRIVATE_ERROR = "SYNTHETIC_SERVICE_PRIVATE_EXCEPTION"
CHILD = r"""
import json, os, socket, sys, threading, urllib.request
payload = json.loads(sys.stdin.readline())
sys.path.insert(0, payload["candidate"])
import httpx
from tools import first_release_service as launcher

def forbidden(*args, **kwargs):
    raise AssertionError("SERVICE_TEST_EXTERNAL_HTTP_FORBIDDEN")

httpx.HTTPTransport.handle_request = forbidden
urllib.request.urlopen = forbidden
original_stdout = sys.stdout
finished, background_ready = threading.Event(), threading.Event()
background_status = []
background = None

def signal(kind, alive):
    original_stdout.write(json.dumps({"state": kind, "background_alive": alive}) + "\n")
    original_stdout.flush()

class FlushHandshake:
    def write(self, value):
        return original_stdout.write(value)
    def flush(self):
        if finished.is_set():
            signal("native_finished", background.is_alive())
            if sys.stdin.readline().strip() != "exit":
                raise AssertionError("SERVICE_TEST_EXIT_ACK_REQUIRED")
        return original_stdout.flush()
    def __getattr__(self, name):
        return getattr(original_stdout, name)

def commit_source(suffix):
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.repositories.postgres import PostgresRepository
    repo = PostgresRepository(os.environ["ZHIMING_DATABASE_URL"], initialize=False, max_size=1)
    try:
        MemoryService(repo).receive("synthetic", content="SYNTHETIC_SERVICE_BODY", channel="synthetic",
            source_id=payload["source"] + suffix)
    finally:
        repo.close()

def background_work():
    try:
        commit_source("-background")
        background_status.append(True)
    except BaseException:
        sys.stderr.write("SERVICE_TEST_BACKGROUND_COMMIT_FAILED\n")
    finally:
        background_ready.set()
    threading.Event().wait()

def native(binding, native_args):
    global background
    sys.stdout = FlushHandshake()
    try:
        commit_source("-main")
        background = threading.Thread(target=background_work, daemon=False)
        background.start()
        if not background_ready.wait(10) or background_status != [True]:
            raise AssertionError("SERVICE_TEST_BACKGROUND_COMMIT_FAILED")
        signal("native_ready", background.is_alive())
        if sys.stdin.readline().strip() != "return":
            raise AssertionError("SERVICE_TEST_NATIVE_ACK_REQUIRED")
        if payload["mode"] == "raise":
            raise RuntimeError("SYNTHETIC_SERVICE_PRIVATE_EXCEPTION")
    finally:
        finished.set()

launcher._native = native
raise SystemExit(launcher.main(payload["arguments"]))
"""


def child_environment(dsn: str) -> dict[str, str]:
    value = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    value.update(
        ZHIMING_DATABASE_URL=dsn,
        PYTHONPATH=str(ROOT),
        PYTHONIOENCODING="utf-8",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        CORE_FEISHU_ENABLED="false",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TZ="Asia/Tokyo",
    )
    assert not any(key.startswith("PG") or "ADMIN_DSN" in key or key == "CORE_TEST_DSN" for key in value)
    return value


class Child:
    def __init__(self, process: subprocess.Popen[str]):
        self.process, self.lines, self.events = process, [], queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        for line in self.process.stdout:
            self.lines.append(line)
            self.events.put(line)

    def state(self, expected: str) -> dict[str, Any]:
        line = self.events.get(timeout=20)
        value = json.loads(line)
        assert value == {"state": expected, "background_alive": True}
        assert self.process.poll() is None
        return value

    def send(self, value: str) -> None:
        self.process.stdin.write(value + "\n")
        self.process.stdin.flush()

    def finish(self, code: int) -> tuple[str, str]:
        assert self.process.wait(timeout=20) == code
        self.reader.join(timeout=2)
        assert not self.reader.is_alive()
        return "".join(self.lines), self.process.stderr.read()


@contextmanager
def service_child(bound: Any, *, mode: str = "return", arguments: list[str] | None = None):
    process = subprocess.Popen(
        [sys.executable, "-u", "-B", "-X", "utf8", "-c", CHILD],
        cwd=ROOT,
        env=child_environment(bound.writer_dsn),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    child = Child(process)
    try:
        child.send(
            json.dumps(
                {
                    "candidate": str(ROOT),
                    "arguments": arguments or [*bound.arguments, "--run"],
                    "source": bound.source,
                    "mode": mode,
                }
            )
        )
        yield child
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()

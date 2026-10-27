"""Only loopback HTTP and a clean isolated PG producer are permitted in these probes."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

HEADERS = {"X-Token": "synthetic-event-owner"}


def isolate(monkeypatch: Any) -> None:
    original = httpx.Client.send

    def local_only(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        if request.url.host != "127.0.0.1":
            raise AssertionError("event HTTP probes permit only loopback")
        return original(self, request, *args, **kwargs)

    async def no_external(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("event HTTP probes do not use async external clients")

    monkeypatch.setattr(httpx.Client, "send", local_only)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_external)
    for name in (
        "KIMI_API_KEY",
        "MOONSHOT_API_KEY",
        "OPENAI_API_KEY",
        "LANGSMITH_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("MINGJING_TOKEN", HEADERS["X-Token"])
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv(
        "ZHIMING_TOKEN_OWNERS", json.dumps({"synthetic-event-bob": "bob"})
    )


def until(predicate: Any, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("bounded local HTTP event condition did not occur")
        time.sleep(0.01)


def frame(lines: Any) -> dict[str, Any]:
    values = {}
    for line in lines:
        if line == "" and "data" in values:
            return {"type": values["event"], "data": json.loads(values["data"])}
        if ": " in line:
            key, value = line.split(": ", 1)
            values[key] = value
    raise AssertionError("event stream ended without the expected frame")


def decoded(text: str) -> list[dict[str, Any]]:
    result = []
    for block in text.split("\n\n"):
        if "\nevent: " in "\n" + block:
            result.append(frame(iter([*block.splitlines(), ""])))
    return result


def producer(
    repo: Any, run: dict[str, Any], *, text: str = "合成跨进程片段"
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    helper = Path(__file__).with_name("event_http_producer.py")
    env = {
        key: value
        for key, value in os.environ.items()
        if not re.search(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD)$", key)
        and not key.startswith("PG")
    }
    env.update(
        TZ="Asia/Tokyo",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
    )
    command = "import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2],run_name='__main__')"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-X",
            "pycache_prefix=" + os.path.abspath(os.devnull),
            "-c",
            command,
            str(root),
            str(helper),
        ],
        input=json.dumps(
            dict(
                dsn=repo.dsn,
                schema=repo.schema,
                owner=run["owner"],
                ident=run["id"],
                text=text,
            )
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=10,
        env=env,
    )
    assert result.returncode == 0, "isolated synthetic event producer failed"
    return json.loads(result.stdout)

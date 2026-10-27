"""Deny network transports in the preview process and its chart workers."""

from __future__ import annotations

import os
import runpy
import socket
import subprocess
import sys
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


def denied(*args, **kwargs):
    raise RuntimeError("scripted_preview_network_transport_disabled")


@contextmanager
def offline_runtime():
    before = dict(os.environ)
    for key in list(os.environ):
        if "API_KEY" in key.upper() or key.upper().startswith(
            ("LANGSMITH", "LANGCHAIN")
        ):
            os.environ.pop(key, None)
    os.environ.update(
        PYTHONUTF8="1", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false"
    )
    original = subprocess.run
    bootstrap = str(Path(__file__).resolve())
    charts = Path(__file__).resolve().parents[1]

    def run(args, *positional, **kwargs):
        if not isinstance(args, list) or len(args) != 4 or args[1:3] != ["-X", "utf8"]:
            raise RuntimeError("scripted_preview_unknown_child_process")
        worker = Path(args[3]).resolve()
        if worker.parent != charts or worker.name not in ("worker.py", "p8_worker.py"):
            raise RuntimeError("scripted_preview_unknown_chart_worker")
        return original(
            [args[0], "-X", "utf8", bootstrap, str(worker)], *positional, **kwargs
        )

    try:
        with (
            patch.object(socket, "create_connection", denied),
            patch.object(socket.socket, "connect", denied),
            patch.object(socket.socket, "connect_ex", denied),
            patch.object(urllib.request, "urlopen", denied),
            patch.object(subprocess, "run", run),
        ):
            yield
    finally:
        os.environ.clear()
        os.environ.update(before)


def main() -> None:
    worker = Path(sys.argv[1]).resolve()
    charts = Path(__file__).resolve().parents[1]
    if worker.parent != charts or worker.name not in ("worker.py", "p8_worker.py"):
        raise ValueError("scripted_preview_unknown_chart_worker")
    socket.create_connection = denied
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    urllib.request.urlopen = denied
    sys.argv = [str(worker)]
    runpy.run_path(str(worker), run_name="__main__")


if __name__ == "__main__":
    main()

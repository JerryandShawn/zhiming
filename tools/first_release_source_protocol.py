"""Bounded parent pipe I/O and owned-child cleanup; never a source permission."""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any

from tools.first_release_contracts import RestoreRejected, require


def prefer(first: BaseException | None, later: BaseException | None) -> BaseException | None:
    if isinstance(first, (KeyboardInterrupt, SystemExit, GeneratorExit)):
        return first
    if isinstance(later, (KeyboardInterrupt, SystemExit, GeneratorExit)):
        return later
    return first if first is not None else later


def send(process: Any, value: dict[str, Any]) -> None:
    try:
        process.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
        process.stdin.flush()
    except (OSError, ValueError):
        raise RestoreRejected("SOURCE_REPLAY_PROTOCOL_WRITE_FAILED") from None


def read(process: Any, deadline: float) -> dict[str, Any]:
    messages: queue.Queue[Any] = queue.Queue(maxsize=1)

    def once() -> None:
        try:
            messages.put(process.stdout.readline(65537))
        except Exception:
            messages.put(None)

    threading.Thread(target=once, daemon=True).start()
    try:
        raw = messages.get(timeout=max(0.01, deadline - time.monotonic()))
        require(type(raw) is str and len(raw) <= 65536 and raw.endswith("\n"), "SOURCE_REPLAY_PROTOCOL_LINE")
        value = json.loads(raw)
        require(type(value) is dict, "SOURCE_REPLAY_PROTOCOL_FIELDS")
    except (queue.Empty, ValueError, TypeError):
        raise RestoreRejected("SOURCE_REPLAY_PROTOCOL_TIMEOUT_OR_INVALID") from None
    if value.get("event") == "blocked":
        # Neither child stderr nor arbitrary child-provided messages cross this boundary.
        raise RestoreRejected("SOURCE_REPLAY_WORKER_REJECTED")
    return value


def cleanup(process: Any) -> BaseException | None:
    failure: BaseException | None = None
    actions = [
        lambda: process.kill() if process.poll() is None else None,
        lambda: process.wait(timeout=5),
        process.stdin.close,
        process.stdout.close,
    ]
    for action in actions:
        try:
            action()
        except BaseException as error:
            safe = (
                error
                if isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit))
                else RestoreRejected("SOURCE_REPLAY_PROCESS_CLEANUP_FAILED")
            )
            failure = prefer(failure, safe)
    return failure

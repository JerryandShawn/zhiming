"""Atomic local call ledger shared by evaluators using one membership account."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO


def _file_lock(handle: BinaryIO, *, unlock: bool = False) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK if unlock else msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN if unlock else fcntl.LOCK_EX)


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "calls": [], "runs": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        valid = (
            isinstance(state, dict)
            and state.get("version") == 1
            and isinstance(state.get("calls"), list)
            and isinstance(state.get("runs"), dict)
        )
    except (OSError, ValueError, TypeError):
        valid = False
    if not valid:
        raise RuntimeError("会员调用账本无效；停止发送，保留原文件供核查")
    return state


def _write(path: Path, state: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        pending = Path(handle.name)
        json.dump(state, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


@contextmanager
def ledger_transaction(path: Path) -> Iterator[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        _file_lock(handle)
        try:
            state = _read(path)
            try:
                yield state
            finally:
                _write(path, state)
        finally:
            _file_lock(handle, unlock=True)

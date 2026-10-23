"""Real cooperative locks; existing application writers do not yet implement this protocol."""

from __future__ import annotations

import ctypes
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from tools.first_release_contracts import ordinary, require


def _windows(handle: Any, *, exclusive: bool, unlock: bool) -> None:
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    value, overlap = (
        wintypes.HANDLE(msvcrt.get_osfhandle(handle.fileno())),
        Overlapped(),
    )
    if unlock:
        function = api.UnlockFileEx
        function.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(Overlapped),
        ]
        arguments = (value, 0, 1, 0, ctypes.byref(overlap))
    else:
        function = api.LockFileEx
        function.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(Overlapped),
        ]
        arguments = (value, 1 | (2 if exclusive else 0), 0, 1, 0, ctypes.byref(overlap))
    function.restype = wintypes.BOOL
    require(
        bool(function(*arguments)),
        "INCREMENTAL_FILE_UNLOCK_FAILED" if unlock else "INCREMENTAL_FILE_FENCE_BUSY",
    )


@contextmanager
def file_lock(path: Path, *, exclusive: bool) -> Iterator[None]:
    ordinary(path.parent, directory=True)
    if path.exists():
        ordinary(path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "r+b", buffering=0) as handle:
        ordinary(path)
        observed, opened = path.stat(), os.fstat(handle.fileno())
        require(
            (observed.st_dev, observed.st_ino) == (opened.st_dev, opened.st_ino),
            "INCREMENTAL_FENCE_PATH_CHANGED",
        )
        if os.name == "nt":
            _windows(handle, exclusive=exclusive, unlock=False)
        else:
            import fcntl

            try:
                fcntl.flock(
                    handle.fileno(),
                    (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB,
                )
            except BlockingIOError:
                require(False, "INCREMENTAL_FILE_FENCE_BUSY")
        try:
            yield
        finally:
            if os.name == "nt":
                _windows(handle, exclusive=exclusive, unlock=True)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def pg_lock(connection: Any, key: str, *, exclusive: bool) -> Iterator[None]:
    suffix = "" if exclusive else "_shared"
    locked = connection.execute(
        "SELECT pg_try_advisory_lock" + suffix + "(hashtextextended(%s,0)) AS ok",
        (key,),
    )
    require(locked.fetchone()["ok"], "INCREMENTAL_PG_FENCE_BUSY")
    try:
        yield
    finally:
        connection.execute("SELECT pg_advisory_unlock" + suffix + "(hashtextextended(%s,0))", (key,))


@contextmanager
def cooperative_writer(connection: Any, path: Path, key: str, maintenance: Path) -> Iterator[None]:
    with file_lock(path, exclusive=False), pg_lock(connection, key, exclusive=False):
        require(not maintenance.exists(), "INCREMENTAL_MAINTENANCE_RETAINED")
        yield

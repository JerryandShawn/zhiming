"""Resolve reviewed host executables without consulting a mutable PATH."""

from __future__ import annotations

import os
from pathlib import Path

from tools.b1_runtime_trust import inspect_core_venv
from tools.core_incremental_contracts import TARGET, require

CANDIDATES = {
    "systemctl": ("/usr/bin/systemctl", "/bin/systemctl"),
    "pg_dump": (
        "/usr/lib/postgresql/15/bin/pg_dump",
        "/usr/pgsql-15/bin/pg_dump",
        "/usr/local/bin/pg_dump",
        "/usr/bin/pg_dump",
    ),
    "pg_restore": (
        "/usr/lib/postgresql/15/bin/pg_restore",
        "/usr/pgsql-15/bin/pg_restore",
        "/usr/local/bin/pg_restore",
        "/usr/bin/pg_restore",
    ),
}


def executable(name: str) -> str:
    candidate_python = "/root/zhiming-core-releases/" + TARGET + "/venv/core/bin/python"
    candidates = CANDIDATES.get(name, (candidate_python,) if name == candidate_python else ())
    require(candidates, "HOST_COMMAND_NOT_ALLOWED")
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        for item in (path, *path.parents, resolved, *resolved.parents):
            stat = item.stat()
            require(stat.st_uid == 0 and stat.st_mode & 0o022 == 0, "HOST_EXECUTABLE_NOT_TRUSTED")
        require(os.access(resolved, os.X_OK), "HOST_EXECUTABLE_NOT_EXECUTABLE")
        if name == candidate_python:
            inspect_core_venv()
        # Preserve venv discovery: executing the resolved system Python loses it.
        return str(path) if name == candidate_python else str(resolved)
    require(False, "HOST_EXECUTABLE_MISSING")
    raise AssertionError("require always raises")

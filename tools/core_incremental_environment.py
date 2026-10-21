"""Retarget only the reviewed chart interpreter; all secret bytes stay private."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from tools.core_incremental_contracts import PREVIOUS, RELEASE_ROOT, Request, require
from tools.core_incremental_files import ENV_FILES, HostFiles, file_sha, private_write, regular


def chart_environment(files: HostFiles, request: Request, backup: Path) -> dict[str, Any]:
    name = ENV_FILES[-1] if request.scope == "live" else "/root/zhiming-core-secrets/stage-b1-upgrade-runtime.env"
    path = files.path(name)
    regular(path, private=True)
    original = path.read_bytes()
    lines = original.decode("utf-8").splitlines(keepends=True)
    positions = [index for index, line in enumerate(lines) if line.strip().startswith("CHART_PYTHON=")]
    require(len(positions) == 1, "EXACT_CHART_INTERPRETER_REQUIRED")
    index = positions[0]
    line = lines[index]
    tokens = shlex.split(line.strip().partition("=")[2], comments=False)
    old = f"{RELEASE_ROOT}/{PREVIOUS}/venv/charts/bin/python"
    new = request.release + "/venv/charts/bin/python"
    require(len(tokens) == 1 and tokens[0] in {old, new}, "UNREVIEWED_CHART_INTERPRETER")
    before = file_sha(path)
    if tokens[0] != new:
        private_write(backup, original)
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        lines[index] = "CHART_PYTHON=" + new + ending
        private_write(path, "".join(lines).encode("utf-8"), replace=True)
    return {
        "path": name,
        "before_sha256": before,
        "after_sha256": file_sha(path),
        "changed": tokens[0] != new,
        "chart_python": new,
    }

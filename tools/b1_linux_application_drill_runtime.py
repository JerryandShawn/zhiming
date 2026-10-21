"""Read the actual candidate interpreter and exact Core lock; never install anything."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import platform
import re
import sys
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from tools.b1_linux_application_drill_contracts import ApplicationBlocked, ApplicationRequest, require
from tools.b1_linux_application_drill_origins import verify_third_party_origins

CORE_LOCK_SHA256 = "d945dfdf75459bfff6d2903ff5b1e3fb1983619102d806f2c969eb339482e4b9"


def dependencies(expected: dict[str, str], extras: dict[str, list[str]]) -> int:
    pins = {canonicalize_name(name): version for name, version in expected.items()}
    enabled_extras = {canonicalize_name(name): set(value) for name, value in extras.items()}
    queue, visited, checked = list(pins), set(), set()
    while queue:
        name = queue.pop()
        enabled = enabled_extras.setdefault(name, set())
        signature = (name, tuple(sorted(enabled)))
        if signature in visited:
            continue
        visited.add(signature)
        for raw in importlib.metadata.requires(name) or []:
            dependency = Requirement(raw)
            required = not dependency.marker or any(
                dependency.marker.evaluate({"extra": extra}) for extra in ["", *enabled]
            )
            if not required:
                continue
            require(not dependency.url, "CORE_UNPINNED_DEPENDENCY_URL")
            key = canonicalize_name(dependency.name)
            require(key in pins, "CORE_UNPINNED_DEPENDENCY")
            try:
                installed = importlib.metadata.version(dependency.name)
            except importlib.metadata.PackageNotFoundError:
                raise ApplicationBlocked("CORE_DEPENDENCY_MISSING") from None
            require(not dependency.specifier or installed in dependency.specifier, "CORE_DEPENDENCY_VERSION")
            child = enabled_extras.setdefault(key, set())
            if dependency.extras - child:
                child.update(dependency.extras)
                queue.append(key)
            checked.add((name, raw))
    return len(checked)


def critical_imports(request: ApplicationRequest) -> list[str]:
    names = [
        "psycopg",
        "langgraph.graph",
        "langgraph.checkpoint.postgres",
        "pydantic",
        "mingjing_core.repositories.postgres",
        "mingjing_core.application.memory",
        "mingjing_core.runtime",
    ]
    modules = {}
    for name in names:
        value = importlib.import_module(name)
        require(getattr(value, "__file__", None), "APPLICATION_IMPORT_ORIGIN_MISSING")
        if name.startswith("mingjing_core."):
            require(
                Path(value.__file__).resolve().is_relative_to(request.candidate_source.resolve()),
                "APPLICATION_IMPORT_OUTSIDE_CANDIDATE",
            )
        modules[name] = value
    verify_third_party_origins(request, modules)
    return names


def runtime_capability(request: ApplicationRequest) -> dict[str, Any]:
    request.validate()
    require(request.local_drill or platform.system() == "Linux", "LINUX_APPLICATION_RUNTIME_REQUIRED")
    require(sys.version_info[:2] == (3, 11), "CORE_PYTHON311_REQUIRED")
    require(Path(sys.executable).resolve() == request.candidate_python.resolve(), "APPLICATION_INTERPRETER_CHANGED")
    source = (request.candidate_source / "requirements-core.lock").read_bytes()
    require(hashlib.sha256(source).hexdigest() == CORE_LOCK_SHA256, "APPLICATION_CORE_LOCK_CHANGED")
    expected, extras = {}, {}
    for line in source.decode().splitlines():
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[([^\]]+)\])?==([^\s\\]+)\s*(?:\\)?", line)
        if match:
            expected[match[1]] = match[3]
            extras[match[1]] = match[2].split(",") if match[2] else []
    require(expected, "APPLICATION_CORE_LOCK_EMPTY")
    try:
        actual = {name: importlib.metadata.version(name) for name in expected}
    except importlib.metadata.PackageNotFoundError:
        raise ApplicationBlocked("CORE_LOCKED_PACKAGE_MISSING") from None
    require(actual == expected, "CORE_LOCKED_PACKAGE_VERSION")
    checked = dependencies(expected, extras)
    imports = critical_imports(request)
    return {
        "os": platform.system(),
        "python": platform.python_version(),
        "interpreter_sha256": hashlib.sha256(request.candidate_python.resolve().read_bytes()).hexdigest(),
        "core_lock_sha256": CORE_LOCK_SHA256,
        "locked_packages": len(actual),
        "dependency_check": "installed-metadata-requires-dist",
        "checked_dependencies": checked,
        "critical_imports": imports,
        "admissible_linux": not request.local_drill and platform.system() == "Linux",
        "database_connections": 0,
        "packages_installed": 0,
    }

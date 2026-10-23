"""Post-import location diagnostics; neither wheel integrity nor safe-import attestation."""

from __future__ import annotations

import sys
import sysconfig
from collections.abc import Mapping
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

from tools.b1_linux_application_drill_contracts import ApplicationBlocked, ApplicationRequest, require
from tools.core_incremental_contracts import RELEASE_ROOT, TARGET

FORMAL_CORE = Path(RELEASE_ROOT) / TARGET / "venv/core"
FORMAL_SITE = FORMAL_CORE / "lib/python3.11/site-packages"
LEAVES = ("psycopg", "langgraph.graph", "langgraph.checkpoint.postgres", "pydantic")
NAMESPACES = ("langgraph", "langgraph.checkpoint")
MAX_LOCATIONS = 16
MAX_PATH_LENGTH = 4096


def checked_path(value: Any, *, directory: bool = False) -> Path:
    require(isinstance(value, str) and 0 < len(value) <= MAX_PATH_LENGTH, "APPLICATION_DEPENDENCY_IMPORT_ORIGIN")
    require("\x00" not in value, "APPLICATION_DEPENDENCY_IMPORT_ORIGIN")
    path = Path(value)
    require(path.is_absolute(), "APPLICATION_DEPENDENCY_IMPORT_ORIGIN")
    path = path.resolve(strict=True)
    require(path.is_dir() if directory else path.is_file(), "APPLICATION_DEPENDENCY_IMPORT_ORIGIN")
    return path


def package_roots(request: ApplicationRequest) -> tuple[Path, ...]:
    prefix = checked_path(sys.prefix, directory=True)
    roots = tuple(sorted({checked_path(sysconfig.get_path(name), directory=True) for name in ("purelib", "platlib")}))
    if not request.local_drill:
        expected = FORMAL_SITE.resolve(strict=True)
        require(prefix == FORMAL_CORE.resolve(strict=True) and roots == (expected,), "APPLICATION_DEPENDENCY_ROOTS")
    else:
        require(all(path != prefix and path.is_relative_to(prefix) for path in roots), "APPLICATION_DEPENDENCY_ROOTS")
    return roots


def inside(path: Path, roots: tuple[Path, ...]) -> None:
    require(any(path.is_relative_to(root) for root in roots), "APPLICATION_DEPENDENCY_OUTSIDE_VENV")


def locations(value: Any, roots: tuple[Path, ...]) -> tuple[Path, ...]:
    require(value is not None and not isinstance(value, (str, bytes)), "APPLICATION_DEPENDENCY_PACKAGE_PATH")
    result = []
    for item in value:
        require(len(result) < MAX_LOCATIONS, "APPLICATION_DEPENDENCY_PATH_LIMIT")
        path = checked_path(item, directory=True)
        inside(path, roots)
        result.append(path)
    require(result, "APPLICATION_DEPENDENCY_PACKAGE_PATH")
    return tuple(sorted(set(result)))


def check_module(name: str, module: ModuleType, roots: tuple[Path, ...]) -> None:
    spec = getattr(module, "__spec__", None)
    require(isinstance(spec, ModuleSpec) and spec.name == name, "APPLICATION_DEPENDENCY_IMPORT_SPEC")
    filename = getattr(module, "__file__", None)
    if filename is None:
        require(name in NAMESPACES and spec.origin is None, "APPLICATION_DEPENDENCY_NAMESPACE")
        require(spec.submodule_search_locations is not None, "APPLICATION_DEPENDENCY_PACKAGE_PATH")
    else:
        path = checked_path(filename)
        require(path == checked_path(spec.origin), "APPLICATION_DEPENDENCY_IMPORT_SPEC")
        inside(path, roots)
    observed_paths = getattr(module, "__path__", None)
    if spec.submodule_search_locations is None:
        require(observed_paths is None, "APPLICATION_DEPENDENCY_PACKAGE_PATH")
    else:
        expected = locations(spec.submodule_search_locations, roots)
        require(locations(observed_paths, roots) == expected, "APPLICATION_DEPENDENCY_PACKAGE_PATH")


def verify_third_party_origins(request: ApplicationRequest, modules: Mapping[str, ModuleType]) -> None:
    """Observe actual modules after import; caller cannot select an expected directory."""
    try:
        roots = package_roots(request)
        for name in LEAVES:
            require(name in modules, "APPLICATION_DEPENDENCY_IMPORT_SPEC")
            check_module(name, modules[name], roots)
        for name in NAMESPACES:
            require(name in sys.modules, "APPLICATION_DEPENDENCY_NAMESPACE")
            check_module(name, sys.modules[name], roots)
    except ApplicationBlocked:
        raise
    except (OSError, ValueError, TypeError, RuntimeError):
        raise ApplicationBlocked("APPLICATION_DEPENDENCY_IMPORT_ORIGIN") from None

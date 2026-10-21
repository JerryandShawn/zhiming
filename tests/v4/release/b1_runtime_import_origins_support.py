"""Temporary-directory and ModuleSpec models do not attest Linux or package bytes."""

from __future__ import annotations

from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from tools.b1_linux_application_drill_origins import LEAVES, NAMESPACES


def module_at(name: str, site: Path, *, namespace: bool = False) -> ModuleType:
    directory = site.joinpath(*name.split("."))
    directory.mkdir(parents=True, exist_ok=True)
    value = ModuleType(name)
    if namespace:
        value.__file__ = None
        value.__spec__ = ModuleSpec(name, loader=None, is_package=True)
    else:
        path = directory / "__init__.py"
        path.write_text("# synthetic, never imported\n", encoding="utf-8")
        value.__file__ = str(path)
        value.__spec__ = ModuleSpec(name, loader=None, origin=str(path), is_package=True)
    value.__spec__.submodule_search_locations = [str(directory)]
    value.__path__ = [str(directory)]
    return value


def modules_at(site: Path) -> dict[str, ModuleType]:
    return {name: module_at(name, site, namespace=name in NAMESPACES) for name in (*LEAVES, *NAMESPACES)}

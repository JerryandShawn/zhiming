"""Read explicit IANA zone data with traceable bytes; never guess a city/offset."""

from __future__ import annotations

import hashlib
import importlib
import io
import os
import re
import zoneinfo
from importlib.resources import files
from pathlib import Path
from typing import Any


def load_zone(key: str) -> tuple[zoneinfo.ZoneInfo, dict[str, Any]]:
    if not isinstance(key, str) or not re.fullmatch(
        r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*", key
    ):
        raise ValueError("必须提供明确的IANA出生时区，不能根据城市猜测")
    override = os.environ.get("PYTHONTZPATH")
    if override is not None:
        roots = tuple(Path(root) for root in override.split(os.pathsep) if root)
        if any(not root.is_absolute() for root in roots):
            raise ValueError("显式PYTHONTZPATH必须只含绝对路径，不能静默忽略相对目录")
        if roots:
            loaded = _from_paths(key, roots, "explicit_environment_tzpath")
            if loaded is None:
                raise ValueError("显式PYTHONTZPATH没有所需时区文件，不能改用其它数据源")
            return loaded
        # An explicitly empty search path disables OS data, like ZoneInfo.
        loaded = _from_package(key)
    else:
        loaded = _from_package(key)
        if loaded is None:
            loaded = _from_paths(
                key,
                tuple(Path(root) for root in zoneinfo.TZPATH),
                "system_unpinned_fallback",
            )
    if loaded is None:
        raise ValueError("没有可用的出生时区数据；需要已确认时区及锁定的tzdata")
    return loaded


def _from_paths(
    key: str, roots: tuple[Path, ...], source: str
) -> tuple[zoneinfo.ZoneInfo, dict[str, Any]] | None:
    for root in roots:
        path = root.joinpath(*key.split("/"))
        if path.is_file():
            data = path.read_bytes()
            version_file = Path(root) / "tzdata.zi"
            version = "system_version_not_exposed"
            if version_file.is_file():
                with version_file.open(encoding="utf-8") as stream:
                    first = stream.readline().strip()
                if first.startswith("# version "):
                    version = first.removeprefix("# version ")
            return _loaded(key, data, source, version, None)
    return None


def _from_package(key: str) -> tuple[zoneinfo.ZoneInfo, dict[str, Any]] | None:
    try:
        package = importlib.import_module("tzdata")
        data = files("tzdata.zoneinfo").joinpath(*key.split("/")).read_bytes()
    except (ModuleNotFoundError, FileNotFoundError, IsADirectoryError):
        return None
    return _loaded(
        key, data, "tzdata_package", package.IANA_VERSION, package.__version__
    )


def _loaded(
    key: str, data: bytes, source: str, version: str, package_version: str | None
) -> tuple[zoneinfo.ZoneInfo, dict[str, Any]]:
    try:
        zone = zoneinfo.ZoneInfo.from_file(io.BytesIO(data), key=key)
    except ValueError:
        raise ValueError("出生时区数据格式无效，不能回退为固定偏移") from None
    return zone, {
        "zone": key,
        "source": source,
        "iana_version": version,
        "tzdata_package_version": package_version,
        "zone_sha256": hashlib.sha256(data).hexdigest(),
        "historical_accuracy": "tzdb_convention_not_birth_document_verification",
        "selection_policy": "current_explicit_environment_then_package_then_unpinned_system",
        "source_limits": {
            "tzdata_package": "package_version_recorded; deployment_lock_match_not_checked_here",
            "explicit_environment_tzpath": "caller_selected_files_may_differ_from_package_lock",
            "system_unpinned_fallback": "OS_data_unpinned; cross_platform_equivalence_not_established",
        }[source],
    }

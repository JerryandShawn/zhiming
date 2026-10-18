"""Read explicit IANA zone data with traceable bytes; never guess a city/offset."""

from __future__ import annotations

import hashlib
import importlib
import io
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
    for root in zoneinfo.TZPATH:
        path = Path(root).joinpath(*key.split("/"))
        if path.is_file():
            data = path.read_bytes()
            version_file = Path(root) / "tzdata.zi"
            version = "system_version_not_exposed"
            if version_file.is_file():
                with version_file.open(encoding="utf-8") as stream:
                    first = stream.readline().strip()
                if first.startswith("# version "):
                    version = first.removeprefix("# version ")
            return _loaded(key, data, "explicit_system_tzpath", version, None)
    try:
        package = importlib.import_module("tzdata")
        data = files("tzdata.zoneinfo").joinpath(*key.split("/")).read_bytes()
    except (ModuleNotFoundError, FileNotFoundError, IsADirectoryError):
        raise ValueError(
            "没有可用的出生时区数据；需要已确认时区及锁定的tzdata"
        ) from None
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
    }

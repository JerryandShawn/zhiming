"""Identity and local-file checks shared by K3 installation and runtime loading."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from .context_types import InputMeterUnverified

REVISION = "f831ab66814297da540d832a5235f8e904f29d06"
LOCK_SHA256 = "32cb36f828f63d503dca8f319efd7ee6cecf62680698b64e34bf78b4e660e48a"
DEFAULT_LOCK = Path(__file__).resolve().parents[2] / "k3-tokenizer.lock.json"


def regular_path(path: Path, *, allow_missing: bool = False) -> None:
    if not path.is_absolute() or str(path) != os.path.abspath(path):
        raise InputMeterUnverified()
    for parent in (*reversed(path.parents), path):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            raise InputMeterUnverified() from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise InputMeterUnverified()


def read_k3_lock(path: Path = DEFAULT_LOCK) -> dict[str, Any]:
    try:
        regular_path(path)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != LOCK_SHA256:
            raise InputMeterUnverified()
        lock = json.loads(data)
        if lock["revision"] != REVISION or lock["repository"] != "moonshotai/Kimi-K3":
            raise InputMeterUnverified()
        return lock
    except (OSError, ValueError, KeyError, TypeError):
        raise InputMeterUnverified() from None


def verify_artifacts(directory: Path, lock: dict[str, Any]) -> dict[str, bytes]:
    try:
        regular_path(directory)
        if not directory.is_dir():
            raise InputMeterUnverified()
        verified = {}
        for name, expected in lock["files"].items():
            path = directory / name
            regular_path(path)
            if not path.is_file() or path.stat().st_size != expected["size"]:
                raise InputMeterUnverified()
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected["sha256"]:
                raise InputMeterUnverified()
            verified[name] = data
        return verified
    except (OSError, ValueError, KeyError, TypeError):
        raise InputMeterUnverified() from None

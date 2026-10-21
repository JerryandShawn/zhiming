"""Read-only, fixed-Core-venv metadata checks; no package imports or content attestation."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from tools.core_incremental_contracts import RELEASE_ROOT, TARGET

RELEASE = PurePosixPath(RELEASE_ROOT) / TARGET
CORE = RELEASE / "venv/core"
PYTHON = CORE / "bin/python"
CONFIG = CORE / "pyvenv.cfg"
PACKAGES = CORE / "lib/python3.11/site-packages"
PYTHON_LINKS = frozenset(CORE / "bin" / name for name in ("python", "python3", "python3.11"))
MAX_ENTRIES = 100_000
MAX_LINKS = 8
MAX_CONFIG_BYTES = 16_384


class RuntimeTrustRejected(RuntimeError):
    """Only fixed public codes; no path, config, or package content in errors."""


def require(value: object, code: str) -> None:
    if not value:
        raise RuntimeTrustRejected(code)


@dataclass(frozen=True)
class Entry:
    mode: int
    uid: int
    device: int = 0
    inode: int = 0
    size: int = 0
    mtime_ns: int = 0
    ctime_ns: int = 0


def from_stat(value: os.stat_result) -> Entry:
    return Entry(
        value.st_mode,
        value.st_uid,
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


class MetadataReader(Protocol):
    def entry(self, path: PurePosixPath) -> Entry: ...
    def names(self, path: PurePosixPath) -> tuple[str, ...]: ...
    def link(self, path: PurePosixPath) -> str: ...
    def config(self, path: PurePosixPath, expected: Entry) -> str: ...


class ReadOnlyFilesystem:
    def entry(self, path: PurePosixPath) -> Entry:
        return from_stat(Path(path).lstat())

    def names(self, path: PurePosixPath) -> tuple[str, ...]:
        names = []
        with os.scandir(path) as entries:
            for item in entries:
                require(len(names) < MAX_ENTRIES, "VENV_DIRECTORY_LIMIT")
                names.append(item.name)
        return tuple(sorted(names))

    def link(self, path: PurePosixPath) -> str:
        return os.readlink(path)

    def config(self, path: PurePosixPath, expected: Entry) -> str:
        require(path == CONFIG and expected.size <= MAX_CONFIG_BYTES, "VENV_CONFIG_SCOPE")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            require(from_stat(os.fstat(stream.fileno())) == expected, "VENV_METADATA_CHANGED")
            raw = stream.read(MAX_CONFIG_BYTES + 1)
            require(len(raw) <= MAX_CONFIG_BYTES, "VENV_CONFIG_SIZE")
            require(from_stat(os.fstat(stream.fileno())) == expected, "VENV_METADATA_CHANGED")
        return raw.decode("utf-8")


class _Audit:
    def __init__(self, reader: MetadataReader) -> None:
        self.reader = reader
        self.entries: dict[PurePosixPath, Entry] = {}
        self.links: dict[PurePosixPath, str] = {}

    def entry(self, path: PurePosixPath) -> Entry:
        if path not in self.entries:
            require(len(self.entries) < MAX_ENTRIES, "VENV_METADATA_LIMIT")
            self.entries[path] = self.reader.entry(path)
        return self.entries[path]

    def protected(self, path: PurePosixPath, *, link: bool = False) -> Entry:
        for parent in reversed(path.parents):
            row = self.entry(parent)
            require(stat.S_ISDIR(row.mode), "VENV_ANCESTOR_TYPE")
            require(row.uid == 0 and row.mode & 0o022 == 0, "VENV_ANCESTOR_WRITABLE")
        row = self.entry(path)
        require(row.uid == 0, "VENV_NOT_ROOT_OWNED")
        if stat.S_ISLNK(row.mode):
            require(link, "VENV_SYMLINK_NOT_ALLOWED")
        else:
            require(stat.S_ISDIR(row.mode) or stat.S_ISREG(row.mode), "VENV_SPECIAL_FILE")
            require(row.mode & 0o022 == 0, "VENV_GROUP_OR_OTHER_WRITABLE")
        return row

    def target(self, path: PurePosixPath) -> PurePosixPath:
        value = self.reader.link(path)
        require(value and len(value) <= 4096 and "\x00" not in value, "VENV_LINK_TARGET")
        require(path not in self.links or self.links[path] == value, "VENV_LINK_CHANGED")
        self.links[path] = value
        target = PurePosixPath(value)
        return PurePosixPath(posixpath.normpath(str(target if target.is_absolute() else path.parent / target)))

    def interpreter(self, path: PurePosixPath) -> None:
        seen = set()
        for _ in range(MAX_LINKS + 1):
            require(path not in seen, "VENV_LINK_CYCLE")
            require(not path.is_relative_to(RELEASE / "venv/charts"), "VENV_INTERPRETER_SCOPE")
            seen.add(path)
            row = self.protected(path, link=True)
            if not stat.S_ISLNK(row.mode):
                require(stat.S_ISREG(row.mode) and row.mode & 0o111 != 0, "VENV_INTERPRETER_TYPE")
                return
            require(not path.is_relative_to(CORE) or path in PYTHON_LINKS, "VENV_INTERPRETER_LINK")
            require(len(seen) <= MAX_LINKS, "VENV_LINK_LIMIT")
            path = self.target(path)
        raise RuntimeTrustRejected("VENV_LINK_LIMIT")

    def linked_entry(self, path: PurePosixPath) -> None:
        if path == CORE / "lib64":
            require(self.target(path) == CORE / "lib", "VENV_LIB64_TARGET")
            require(stat.S_ISDIR(self.protected(CORE / "lib").mode), "VENV_LIB64_TARGET")
        else:
            require(path in PYTHON_LINKS, "VENV_SYMLINK_NOT_ALLOWED")
            self.interpreter(path)

    def tree(self) -> None:
        pending = [CORE]
        seen = set()
        while pending:
            path = pending.pop()
            require(path != CORE / "bin/pyvenv.cfg", "VENV_CONFIG_SHADOW")
            require(path not in seen, "VENV_DIRECTORY_REPEATED")
            seen.add(path)
            require(len(path.parts) - len(CORE.parts) <= 64, "VENV_DIRECTORY_DEPTH")
            row = self.protected(path, link=path in PYTHON_LINKS or path == CORE / "lib64")
            if stat.S_ISLNK(row.mode):
                self.linked_entry(path)
            elif stat.S_ISDIR(row.mode):
                names = self.reader.names(path)
                require(len(names) <= MAX_ENTRIES and len(pending) + len(names) <= MAX_ENTRIES, "VENV_DIRECTORY_LIMIT")
                require(len(names) == len(set(names)), "VENV_DIRECTORY_DUPLICATE")
                for name in names:
                    require(name not in {"", ".", ".."} and "/" not in name, "VENV_DIRECTORY_MEMBER")
                    pending.append(path / name)

    def configuration(self) -> None:
        row = self.protected(CONFIG)
        require(stat.S_ISREG(row.mode) and row.size <= MAX_CONFIG_BYTES, "VENV_CONFIG_SCOPE")
        text = self.reader.config(CONFIG, row)
        require(len(text.encode("utf-8")) <= MAX_CONFIG_BYTES, "VENV_CONFIG_SIZE")
        settings = []
        for line in text.splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip().casefold() == "include-system-site-packages":
                settings.append(value.strip().casefold())
        require(settings == ["false"], "VENV_SYSTEM_SITE_PACKAGES")

    def finish(self) -> dict[str, Any]:
        for path, observed in sorted(self.entries.items()):
            require(self.reader.entry(path) == observed, "VENV_METADATA_CHANGED")
        for path, observed in sorted(self.links.items()):
            require(self.reader.link(path) == observed, "VENV_LINK_CHANGED")
        metadata = [
            {"path": str(path), **asdict(row), "link": self.links.get(path)}
            for path, row in sorted(self.entries.items())
        ]
        digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        return {
            "schema": "b1-core-venv-metadata-v1",
            "target": TARGET,
            "entries_checked": len(self.entries),
            "symlinks_checked": len(self.links),
            "metadata_sha256": digest,
            "system_site_packages": False,
            "package_content_verified": False,
            "linux_filesystem_observed": False,
            "stage_acceptance": False,
            "publication": False,
        }


def inspect_metadata(reader: MetadataReader) -> dict[str, Any]:
    """Synthetic/injected observations never attest a physical Linux filesystem."""
    try:
        audit = _Audit(reader)
        audit.tree()
        audit.configuration()
        require(stat.S_ISDIR(audit.protected(PACKAGES).mode), "VENV_PACKAGES_DIRECTORY")
        audit.interpreter(PYTHON)
        return audit.finish()
    except (OSError, ValueError):
        raise RuntimeTrustRejected("VENV_METADATA_READ") from None


def _linux_host() -> bool:
    return os.name == "posix" and sys.platform == "linux"


def inspect_core_venv() -> dict[str, Any]:
    """Fixed physical entrypoint: no caller-selected path, trust flag, or mode bypass."""
    require(_linux_host(), "VENV_LINUX_REQUIRED")
    value = inspect_metadata(ReadOnlyFilesystem())
    return dict(value, linux_filesystem_observed=True)

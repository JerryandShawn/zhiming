"""Synthetic Posix metadata only; never an observation of this computer or Linux."""

from __future__ import annotations

import stat
from collections import Counter
from dataclasses import replace
from pathlib import PurePosixPath

from tools.b1_runtime_trust import CONFIG, CORE, PACKAGES, Entry

BASE = PurePosixPath("/opt/b1-synthetic-python/bin/python3.11")


class SyntheticMetadata:
    def __init__(self) -> None:
        self.entries: dict[PurePosixPath, Entry] = {}
        self.links: dict[PurePosixPath, str] = {}
        self.reads: Counter[PurePosixPath] = Counter()
        self.link_reads: Counter[PurePosixPath] = Counter()
        self.config_reads: list[PurePosixPath] = []
        self.text = "include-system-site-packages = false\n"
        self.change_on_repeat: PurePosixPath | None = None
        self.failed_entry: PurePosixPath | None = None
        self.duplicate_directory: PurePosixPath | None = None
        self.change_link_on_repeat: PurePosixPath | None = None

    def directory(self, path: PurePosixPath) -> None:
        for member in (*reversed(path.parents), path):
            self.entries.setdefault(member, Entry(stat.S_IFDIR | 0o755, 0))

    def file(self, path: PurePosixPath, *, mode: int = 0o644, size: int = 0) -> None:
        self.directory(path.parent)
        self.entries[path] = Entry(stat.S_IFREG | mode, 0, size=size)

    def symlink(self, path: PurePosixPath, target: str) -> None:
        self.directory(path.parent)
        self.entries[path] = Entry(stat.S_IFLNK | 0o777, 0, size=len(target))
        self.links[path] = target

    def entry(self, path: PurePosixPath) -> Entry:
        self.reads[path] += 1
        if path == self.failed_entry:
            raise PermissionError("SYNTHETIC_PRIVATE_DIAGNOSTIC_MUST_NOT_ESCAPE")
        if path not in self.entries:
            raise FileNotFoundError("SYNTHETIC_PRIVATE_PATH_MUST_NOT_ESCAPE")
        value = self.entries[path]
        if path == self.change_on_repeat and self.reads[path] > 1:
            return replace(value, mtime_ns=value.mtime_ns + 1)
        return value

    def names(self, path: PurePosixPath) -> tuple[str, ...]:
        if path == self.duplicate_directory:
            return ("bin", "bin")
        return tuple(sorted(member.name for member in self.entries if member != path and member.parent == path))

    def link(self, path: PurePosixPath) -> str:
        self.link_reads[path] += 1
        if path == self.change_link_on_repeat and self.link_reads[path] > 1:
            return "synthetic-changed-link"
        return self.links[path]

    def config(self, path: PurePosixPath, expected: Entry) -> str:
        assert path == CONFIG and expected == self.entries[path], "package content must never be read"
        self.config_reads.append(path)
        return self.text


def valid_metadata() -> SyntheticMetadata:
    value = SyntheticMetadata()
    value.directory(PACKAGES)
    value.file(CONFIG, size=len(value.text.encode()))
    value.file(BASE, mode=0o755)
    value.symlink(CORE / "bin/python", "python3")
    value.symlink(CORE / "bin/python3", str(BASE))
    value.symlink(CORE / "bin/python3.11", "python3")
    value.symlink(CORE / "lib64", "lib")
    value.file(PACKAGES / "synthetic_pkg/__init__.py")
    value.file(PACKAGES / "synthetic_pkg-1.dist-info/METADATA")
    value.file(PACKAGES / "protected.pth")
    return value

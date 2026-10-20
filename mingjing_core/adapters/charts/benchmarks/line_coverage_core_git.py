"""Fixed local Git metadata reads outside target execution only."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from . import line_coverage_manifest as manifest
from . import line_coverage_own_inventory as inventory
from . import line_coverage_own_sources as source

CONFIGS = ("pytest.ini", "requirements-core.lock", "requirements-test.lock")
SHA = re.compile(r"[a-f0-9]{40}")
REV_PARSES = (
    ("rev-parse", "HEAD"),
    ("rev-parse", "--show-object-format"),
    ("rev-parse", "--git-dir"),
    ("rev-parse", "--git-common-dir"),
)
DIFF_TREE = (
    "diff-tree",
    "--stdin",
    "--root",
    "--no-commit-id",
    "-r",
    "-m",
    "-z",
    "--diff-filter=D",
    "--no-renames",
    "--name-only",
)


def valid_arguments(args: tuple[str, ...], payload: bytes | None) -> None:
    if args in REV_PARSES:
        valid = payload is None
    elif len(args) == 3 and args[:2] == ("rev-parse", "--verify"):
        valid = (
            bool(re.fullmatch(r"[a-f0-9]{40}\^\{commit\}", args[2])) and payload is None
        )
    elif len(args) == 2 and args[0] == "rev-parse":
        valid = (
            bool(
                re.fullmatch(
                    r"[a-f0-9]{40}:(?:pytest\.ini|requirements-core\.lock|requirements-test\.lock)",
                    args[1],
                )
            )
            and payload is None
        )
    elif args[:1] == ("merge-base",):
        valid = (
            len(args) == 3
            and all(SHA.fullmatch(x) for x in args[1:])
            and payload is None
        )
    elif args[:3] == ("ls-tree", "-r", "-z"):
        valid = len(args) == 4 and bool(SHA.fullmatch(args[3])) and payload is None
    elif args[:2] == ("rev-list", "--ancestry-path"):
        valid = (
            len(args) == 4
            and args[-1] == "--"
            and bool(re.fullmatch(r"[a-f0-9]{40}\.\.[a-f0-9]{40}", args[2]))
            and payload is None
        )
    elif args == ("cat-file", "--batch") or args == DIFF_TREE:
        valid = isinstance(payload, bytes) and bool(
            re.fullmatch(rb"(?:[a-f0-9]{40}\n)*", payload)
        )
    elif args[:4] == ("diff", "--name-status", "-z", "--no-renames"):
        valid = (
            len(args) == 8
            and all(SHA.fullmatch(x) for x in args[4:6])
            and args[6:] == ("--", "*.py")
            and payload is None
        )
    elif args[:4] == ("diff", "--name-only", "-z", "--no-renames"):
        valid = (
            len(args) == 6
            and all(SHA.fullmatch(x) for x in args[4:])
            and payload is None
        )
    elif args == ("ls-files", "--others", "--exclude-standard", "-z", "--", "*.py"):
        valid = payload is None
    else:
        valid = False
    if not valid:
        raise ValueError("b1_git_arguments_not_allowlisted")


def safe_environment() -> dict[str, str]:
    result = {
        key: value
        for key, value in os.environ.items()
        if not any(
            word in key.upper()
            for word in (
                "KEY",
                "TOKEN",
                "SECRET",
                "PASSWORD",
                "DSN",
                "DATABASE",
                "LANGCHAIN",
                "LANGSMITH",
            )
        )
        and not key.upper().startswith(
            ("GIT_", "PYTEST_", "KIMI_", "OPENAI_", "ANTHROPIC_")
        )
    }
    result.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_OPTIONAL_LOCKS="0",
    )
    return result


class MetadataGit:
    def __init__(self, root: Path, active: Callable[[], bool]) -> None:
        self.root = root.resolve()
        binary = shutil.which("git")
        if self.root != manifest.ROOT or binary is None:
            raise ValueError("b1_fixed_git_repository_required")
        self.binary = Path(binary).resolve()
        self.sha256 = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.active = active
        self.environment = safe_environment()
        self._run = subprocess.run
        self.calls = 0
        self.config_files: dict[str, str] = {}
        self.config_files = self.configuration()

    def configuration(self) -> dict[str, str]:
        git_dir = Path(self.read(self.root, "rev-parse", "--git-dir").decode().strip())
        common = Path(
            self.read(self.root, "rev-parse", "--git-common-dir").decode().strip()
        )
        git_dir = git_dir if git_dir.is_absolute() else self.root / git_dir
        common = common if common.is_absolute() else self.root / common
        paths = [self.root / ".git", common / "config", git_dir / "config.worktree"]
        result = {}
        for path in paths:
            if path.is_file():
                raw = path.read_bytes()
                if path.name.startswith("config") and re.search(
                    rb"(?im)^\s*\[\s*include", raw
                ):
                    raise ValueError("b1_git_include_requires_review")
                result[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
        return result

    def assert_configuration(self) -> None:
        for name, expected in self.config_files.items():
            path = Path(name)
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected
            ):
                raise ValueError("b1_git_configuration_changed")

    def read(self, root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
        if self.active() or root.resolve() != self.root:
            raise ValueError("b1_git_target_phase_or_repository_refused")
        valid_arguments(args, input_bytes)
        self.assert_configuration()
        if hashlib.sha256(self.binary.read_bytes()).hexdigest() != self.sha256:
            raise ValueError("b1_git_binary_changed")
        try:
            self.calls += 1
            result = self._run(
                [
                    str(self.binary),
                    "-C",
                    str(self.root),
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    "core.hooksPath=" + os.devnull,
                    *args,
                ],
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
                env=self.environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception:
            raise ValueError("b1_git_metadata_read_failed") from None
        if result.returncode:
            raise ValueError("b1_git_metadata_read_failed")
        return result.stdout

    @contextmanager
    def installed(self) -> Iterator[None]:
        with (
            patch.object(manifest, "git_bytes", self.read),
            patch.object(source, "git_bytes", self.read),
            patch.object(inventory, "git_bytes", self.read),
        ):
            yield

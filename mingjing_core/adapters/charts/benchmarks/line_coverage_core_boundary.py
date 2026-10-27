"""Python-layer accidental I/O guards; not an operating-system sandbox."""

from __future__ import annotations

import _thread
import builtins
import contextlib
import io
import os
import subprocess
import sys
import threading
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from .line_coverage_manifest import ROOT

PROCESS_NAMES = (
    "_exit",
    "system",
    "popen",
    "startfile",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execv",
    "execve",
    "execvp",
    "execvpe",
)


class Discard(io.TextIOBase):
    def write(self, value: str) -> int:
        return len(value)


class Gate:
    def __init__(self, allowed_reads: set[str], cache: Path) -> None:
        self.allowed_reads = {
            os.path.normcase(str(Path(path).resolve())) for path in allowed_reads
        }
        self.cache = cache.resolve()
        self.active = False
        self.blocked: Counter[str] = Counter()
        self.skipped_bytecode_probes = 0

    def refuse(self, kind: str):
        self.blocked[kind] += 1
        raise ValueError("b1_target_" + kind + "_refused")

    def process(self, *args, **kwargs):
        self.refuse("process")

    def thread(self, *args, **kwargs):
        self.refuse("thread")

    def input(self, *args, **kwargs):
        self.refuse("input")

    def _open(self, args: tuple) -> None:
        path, mode, flags = args
        writing = (
            isinstance(mode, str) and any(letter in mode for letter in "wax+")
        ) or (
            isinstance(flags, int)
            and flags
            & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        )
        if writing or not isinstance(path, (str, bytes, os.PathLike)):
            self.refuse("file_write_or_descriptor")
        actual = Path(os.fsdecode(path)).resolve()
        if actual != Path(os.fsdecode(path)).absolute():
            self.refuse("file_symlink_or_alias")
        if actual.suffix == ".pyc":
            self.skipped_bytecode_probes += 1
            raise FileNotFoundError("b1_bytecode_probe_skipped_for_source")
        if os.path.normcase(str(actual)) in self.allowed_reads:
            return
        self.refuse("file_read")

    def audit(self, event: str, args: tuple) -> None:
        if not self.active:
            return
        if event == "open":
            self._open(args)
        elif event == "import" and len(args) > 1 and args[1] is not None:
            path = Path(os.fsdecode(args[1]))
            actual = path.resolve()
            if (
                actual != path.absolute()
                or os.path.normcase(str(actual)) not in self.allowed_reads
            ):
                self.refuse("import_source")
        elif event.startswith("socket."):
            self.refuse("network")
        elif (
            event.startswith(("subprocess.", "os.exec", "os.spawn", "os.startfile"))
            or event == "os.system"
        ):
            self.refuse("process")
        elif event in ("sys.settrace", "sys.setprofile"):
            self.refuse("trace_change")
        elif event.startswith("ctypes.") or event == "os.add_dll_directory":
            self.refuse("unregistered_native_load")
        elif event == "os.chdir":
            if Path(args[0]).resolve() != ROOT:
                self.refuse("directory_change")
        elif event in (
            "os.mkdir",
            "os.remove",
            "os.rmdir",
            "os.rename",
            "os.symlink",
            "os.link",
            "os.truncate",
            "os.chmod",
            "os.chown",
            "os.utime",
            "shutil.copyfile",
        ):
            self.refuse("file_mutation")


@contextlib.contextmanager
def boundaries(gate: Gate) -> Iterator[None]:
    sys.addaudithook(gate.audit)
    streams = tuple(
        {
            id(stream): stream
            for stream in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__)
            if stream is not None
        }.values()
    )
    for stream in streams:
        stream.flush()
    original = dict(os.environ)
    for key in tuple(os.environ):
        upper = key.upper()
        if any(
            word in upper
            for word in ("KEY", "TOKEN", "SECRET", "PASSWORD", "DSN", "DATABASE")
        ) or upper.startswith(
            ("KIMI_", "OPENAI_", "ANTHROPIC_", "LANGCHAIN", "LANGSMITH", "PYTEST_")
        ):
            os.environ.pop(key, None)
    os.environ.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTEST_ADDOPTS="",
        LANGCHAIN_TRACING_V2="false",
        LANGSMITH_TRACING="false",
    )
    output_fd = os.open(os.devnull, os.O_WRONLY)
    saved = {fd: os.dup(fd) for fd in (1, 2)}
    try:
        for fd in saved:
            os.dup2(output_fd, fd)
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(Discard()))
            stack.enter_context(contextlib.redirect_stderr(Discard()))
            stack.enter_context(patch.object(sys, "__stdout__", Discard()))
            stack.enter_context(patch.object(sys, "__stderr__", Discard()))
            for name in ("run", "Popen"):
                stack.enter_context(patch.object(subprocess, name, gate.process))
            for name in PROCESS_NAMES:
                if hasattr(os, name):
                    stack.enter_context(patch.object(os, name, gate.process))
            stack.enter_context(patch.object(threading.Thread, "start", gate.thread))
            stack.enter_context(patch.object(_thread, "start_new_thread", gate.thread))
            stack.enter_context(patch.object(builtins, "input", gate.input))
            yield
    finally:
        gate.active = False
        for stream in streams:
            stream.flush()
        for fd, backup in saved.items():
            os.dup2(backup, fd)
            os.close(backup)
        os.close(output_fd)
        os.environ.clear()
        os.environ.update(original)

"""Consumer wiring with captured transport only; no native execution or cleanup proof."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mingjing_core.adapters.charts.benchmarks import line_coverage_core_git as metadata
from mingjing_core.adapters.charts.benchmarks import (
    line_coverage_core_supervisor as supervisor,
)

CONTEXT_KEYS = {
    "__PYVENV_LAUNCHER__",
    "PYTHONHOME",
    "PYTHONEXECUTABLE",
    "PYTHONPATH",
    "VIRTUAL_ENV",
}
ORDINARY = {
    "SYSTEMROOT": "SYNTHETIC_SYSTEMROOT",
    "TEMP": "SYNTHETIC_TEMP",
    "PATH": "SYNTHETIC_PATH",
}


@contextmanager
def inherited_environment() -> Iterator[dict[str, str]]:
    # A normal dict preserves mixed-case names even when the host is Windows.
    mapping = dict(ORDINARY)
    extra = {
        "__PyVenv_Launcher__": "SYNTHETIC_UNTRUSTED_LAUNCHER",
        "pythonhome": "SYNTHETIC_UNTRUSTED_HOME",
        "PythonExecutable": "SYNTHETIC_UNTRUSTED_EXECUTABLE",
        "PyThOnPaTh": "SYNTHETIC_UNTRUSTED_MODULE_PATH",
        "virtual_env": "SYNTHETIC_UNTRUSTED_VENV",
        "SYNTHETIC_API_KEY": "SYNTHETIC_CREDENTIAL",
        "GIT_CONFIG_PARAMETERS": "SYNTHETIC_GIT_OVERRIDE",
        "PYTEST_ADDOPTS": "SYNTHETIC_PYTEST_OVERRIDE",
        "LANGCHAIN_TRACING_V2": "true",
        "LANGSMITH_TRACING": "true",
    }
    original = metadata.os.environ
    with patch.object(metadata.os, "environ", mapping), patch.dict(mapping, extra):
        before = dict(mapping)
        yield mapping
        assert mapping == before
    assert metadata.os.environ is original


def assert_clean_environment(environment: dict[str, str]) -> None:
    names = {key.upper() for key in environment}
    assert not CONTEXT_KEYS.intersection(names)
    assert "SYNTHETIC_API_KEY" not in names
    assert "GIT_CONFIG_PARAMETERS" not in names
    for key, value in ORDINARY.items():
        assert environment[key] == value
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"


def fake_repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "synthetic-repository"
    git_dir = root / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_bytes(b"[core]\n\tbare = false\n")
    binary = tmp_path / "synthetic-git-not-executable.bin"
    binary.write_bytes(b"synthetic data only, never execute this file")
    return root.resolve(), binary.resolve()


def test_metadata_git_constructor_and_read_pass_the_clean_environment(tmp_path) -> None:
    root, binary = fake_repository(tmp_path)
    calls = []
    outputs = {
        ("rev-parse", "--git-dir"): b".git\n",
        ("rev-parse", "--git-common-dir"): b".git\n",
        ("rev-parse", "HEAD"): b"f" * 40 + b"\n",
    }

    def capture_run(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=0, stdout=outputs[tuple(command[7:])])

    with (
        inherited_environment(),
        patch.object(metadata.manifest, "ROOT", root),
        patch.object(metadata.shutil, "which", return_value=str(binary)) as which,
        patch.object(metadata.subprocess, "run", side_effect=capture_run) as transport,
    ):
        reader = metadata.MetadataGit(root, active=lambda: False)
        assert reader.read(root, "rev-parse", "HEAD") == b"f" * 40 + b"\n"
        assert reader.calls == transport.call_count == 3
        which.assert_called_once_with("git")
        assert [tuple(command[7:]) for command, _options in calls] == list(outputs)
        for command, options in calls:
            assert command[:7] == [
                str(binary),
                "-C",
                str(root),
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=" + os.devnull,
            ]
            assert options["env"] is reader.environment
            assert_clean_environment(options["env"])
            assert "PYTEST_ADDOPTS" not in options["env"]
            assert "LANGSMITH_TRACING" not in options["env"]
            assert "LANGCHAIN_TRACING_V2" not in options["env"]
            assert options["input"] is None and options["timeout"] == 10
            assert options["check"] is False


def test_owned_live_taskkill_passes_clean_environment_and_fixed_argv() -> None:
    child = SimpleNamespace(pid=271828, poll=lambda: None)
    job = SimpleNamespace(owns=lambda candidate: candidate is child)
    spec = {"synthetic_specification": True}
    checks, calls = [], []

    def capture_run(command, **options):
        calls.append((command, options, list(checks)))
        return SimpleNamespace(returncode=0)

    with (
        inherited_environment(),
        patch.object(supervisor, "_unchanged", side_effect=checks.append) as unchanged,
        patch.object(
            supervisor.subprocess, "run", side_effect=capture_run
        ) as transport,
    ):
        result = supervisor._kill_tree(child, job, spec)
        unchanged.assert_called_once_with(spec)
        assert transport.call_count == 1 and checks == [spec]
        command, options, checks_before_transport = calls[0]
        assert checks_before_transport == [spec]
        assert command == [str(supervisor.TASKKILL), "/PID", "271828", "/T", "/F"]
        assert_clean_environment(options["env"])
        assert options["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
        assert options["env"]["PYTEST_ADDOPTS"] == ""
        assert options["env"]["PYDANTIC_DISABLE_PLUGINS"] == "__all__"
        assert options["env"]["LANGCHAIN_TRACING_V2"] == "false"
        assert options["env"]["LANGSMITH_TRACING"] == "false"
        assert options["timeout"] == supervisor.TASKKILL_SECONDS
        assert options["shell"] is options["check"] is False
        assert options["creationflags"] == 0x08000000
        assert (
            options["stdin"]
            == options["stdout"]
            == options["stderr"]
            == subprocess.DEVNULL
        )
        assert result == {"taskkill": "attempted_owned_live_launcher", "exit_code": 0}

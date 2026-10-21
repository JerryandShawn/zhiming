"""Eight frozen public CLI behaviours; readiness never becomes a product pass."""

import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from cli_public_support_core_mod import (
    ROOT,
    SUBPROCESS_CODE,
    assert_readiness,
    child_environment,
    no_generation,
    private_path,
)

from mingjing_core.timekit.clock import FrozenClock
from tools.eval_material_v23 import __main__ as cli
from tools.eval_material_v23.loader import MaterialError


@pytest.fixture
def tmp_path() -> Path:
    """Keep this suite's writes private without relying on caller basetemp or OS temp."""
    directory = ROOT / "private" / "mod-week" / "tmp"
    directory.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="cli-public-v23-", dir=directory))


def test_cli01_fixed_clock_generates_only_readiness_independent_of_host_zone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    instant = datetime(2026, 10, 20, 23, 30, tzinfo=UTC)
    reports = []
    for index, at in enumerate((instant, instant.astimezone(ZoneInfo("Asia/Tokyo")))):
        path = private_path(tmp_path, f"new-readiness-{index}.json")
        monkeypatch.setattr(cli, "SystemClock", lambda at=at: FrozenClock(at))
        monkeypatch.setattr(sys, "argv", ["eval-material", "--output", str(path)])
        cli.main()
        reports.append(assert_readiness(path, capsys.readouterr().out))
    assert reports[0] == reports[1]


def test_cli02_existing_report_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = private_path(tmp_path, "existing-report.json")
    original = b'{"synthetic":true,"sentinel":"original"}\r\n'
    path.write_bytes(original)
    no_generation(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["eval-material", "--output", str(path)])
    with pytest.raises(MaterialError, match="^report_requires_new_workspace_path$"):
        cli.main()
    assert path.read_bytes() == original


def test_cli03_absolute_outside_path_is_rejected_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_path(tmp_path, "unused.json")
    outside = ROOT.parent / f"outside-cli-{tmp_path.name}.json"
    assert not outside.exists()
    no_generation(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["eval-material", "--output", str(outside)])
    with pytest.raises(MaterialError, match="^report_requires_new_workspace_path$"):
        cli.main()
    assert not outside.exists()


def test_cli04_relative_dotdot_escape_is_rejected_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_path(tmp_path, "unused.json")
    outside = ROOT.parent / f"dotdot-cli-{tmp_path.name}.json"
    relative = Path(os.path.relpath(outside, tmp_path))
    assert ".." in relative.parts and not outside.exists()
    no_generation(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["eval-material", "--output", str(relative)])
    with pytest.raises(MaterialError, match="^report_requires_new_workspace_path$"):
        cli.main()
    assert not outside.exists()


def test_cli05_missing_parent_is_not_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = private_path(tmp_path, "missing-parent") / "report.json"
    assert not path.parent.exists()
    no_generation(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["eval-material", "--output", str(path)])
    with pytest.raises(MaterialError, match="^report_requires_new_workspace_path$"):
        cli.main()
    assert not path.parent.exists() and not path.exists()


def test_cli06_required_argument_has_argparse_exit_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    no_generation(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["eval-material"])
    with pytest.raises(SystemExit) as caught:
        cli.main()
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert "--output" in captured.err and "required" in captured.err and captured.out == ""


def test_cli07_help_has_argparse_exit_zero_without_generation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    no_generation(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["eval-material", "--help"])
    with pytest.raises(SystemExit) as caught:
        cli.main()
    assert caught.value.code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out and "--output" in captured.out and captured.err == ""


def test_cli08_clean_module_entry_generates_fixed_clock_readiness(tmp_path: Path) -> None:
    path = private_path(tmp_path, "module-entry-report.json")
    result = subprocess.run(
        [sys.executable, "-B", "-c", SUBPROCESS_CODE, str(path)],
        cwd=ROOT,
        env=child_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert result.returncode == 0 and result.stderr == ""
    assert_readiness(path, result.stdout)

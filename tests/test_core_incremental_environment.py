"""Synthetic environment bytes and executable resolution never invoke a host command."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from test_core_incremental_upgrade import fixture

from tools.core_incremental_binaries import executable
from tools.core_incremental_contracts import PREVIOUS, TARGET, Request, UpgradeRejected
from tools.core_incremental_environment import chart_environment
from tools.core_incremental_files import ENV_FILES, HostFiles, private_write, regular


@pytest.fixture
def trusted_mode_fixture() -> Iterator[None]:
    # Windows cannot establish POSIX 0600; these are byte/flow tests only.
    with patch("tools.core_incremental_environment.regular", side_effect=lambda p, private=False: regular(p)):
        yield


def prepare(tmp_path: Path, text: str, scope: str = "live") -> tuple[HostFiles, Request, Path]:
    raw, _ = fixture(scope)
    request, files = Request.parse(raw), HostFiles(tmp_path)
    name = ENV_FILES[-1] if scope == "live" else "/root/zhiming-core-secrets/stage-b1-upgrade-runtime.env"
    path = files.path(name)
    private_write(path, text.encode("utf-8"))
    return files, request, path


@pytest.mark.usefixtures("trusted_mode_fixture")
@pytest.mark.parametrize("scope", ["live", "stage"])
@pytest.mark.parametrize("ending", ["\n", "\r\n", ""])
def test_retarget_only_chart_line_and_preserve_secret_bytes(tmp_path: Path, scope: str, ending: str) -> None:
    unchanged = "# 合成配置\nSYNTHETIC_SECRET=PRIVATE_VALUE\nKIMI_MODEL=k3\n"
    line = f'CHART_PYTHON="/root/zhiming-core-releases/{PREVIOUS}/venv/charts/bin/python"{ending}'
    files, request, path = prepare(tmp_path, unchanged + line, scope)
    backup = tmp_path / "backup" / "runtime.env"
    result = chart_environment(files, request, backup)
    assert result["changed"] and result["before_sha256"] != result["after_sha256"]
    assert backup.read_bytes() == (unchanged + line).encode("utf-8")
    assert path.read_bytes() == (unchanged + f"CHART_PYTHON={request.release}/venv/charts/bin/python{ending}").encode()
    assert "PRIVATE_VALUE" not in str(result)
    repeat = chart_environment(files, request, backup)
    assert repeat["changed"] is False and backup.read_bytes() == (unchanged + line).encode()


@pytest.mark.usefixtures("trusted_mode_fixture")
@pytest.mark.parametrize(
    "chart", ["", "CHART_PYTHON=/other/python\n", "CHART_PYTHON=/one\nCHART_PYTHON=/two\n", "CHART_PYTHON=/one /two\n"]
)
def test_unknown_or_duplicate_chart_interpreter_stops_without_writes(tmp_path: Path, chart: str) -> None:
    files, request, path = prepare(tmp_path, "KIMI_MODEL=k3\n" + chart)
    before = path.read_bytes()
    with pytest.raises(UpgradeRejected):
        chart_environment(files, request, tmp_path / "not-created" / "backup")
    assert path.read_bytes() == before and not (tmp_path / "not-created").exists()


@pytest.mark.parametrize("name", ["ssh", "bash", "cmd", "python", "/tmp/systemctl", "pg_dump;id"])
def test_arbitrary_program_is_rejected_before_subprocess(name: str) -> None:
    with pytest.raises(UpgradeRejected, match="HOST_COMMAND_NOT_ALLOWED"):
        executable(name)


@pytest.mark.parametrize("name", ["systemctl", f"/root/zhiming-core-releases/{TARGET}/venv/core/bin/python"])
def test_reviewed_command_resolves_without_path_and_keeps_venv_identity(name: str) -> None:
    fake = SimpleNamespace(is_file=lambda: True, parents=(), stat=lambda: SimpleNamespace(st_uid=0, st_mode=0o755))
    fake.resolve = lambda **kwargs: fake
    fake.__str__ = lambda: "/trusted/bin"
    with (
        patch("tools.core_incremental_binaries.Path", return_value=fake),
        patch("tools.core_incremental_binaries.os.access", return_value=True),
    ):
        assert executable(name) == str(fake)
    fake.stat = lambda: SimpleNamespace(st_uid=1000, st_mode=0o755)
    with (
        patch("tools.core_incremental_binaries.Path", return_value=fake),
        pytest.raises(UpgradeRejected, match="HOST_EXECUTABLE_NOT_TRUSTED"),
    ):
        executable(name)

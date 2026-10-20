"""Terminal I/O may be substituted; grant state is checked in real isolated PostgreSQL."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from psycopg import sql

from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_runtime import ENVIRONMENT, CentralLocation
from mingjing_core.repositories.postgres import PostgresRepository
from tools import member_start

from .test_quota_guard_pg import configure_central


class TerminalFixture(io.StringIO):
    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        return 0


def terminal(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", TerminalFixture(text + "\n"))
    monkeypatch.setattr("os.isatty", lambda _: True)


def test_redirected_input_and_confirmation_environment_cannot_authorize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("开始 E1 第 1 批\n"))
    monkeypatch.setenv("MEMBER_CONFIRM", "开始 E1 第 1 批")
    with pytest.raises(member_start.ManualStartRejected, match="本机终端"):
        member_start.confirm_local("E1", 1)


@pytest.mark.parametrize("text", ["开始", "同意", "开始 E1 第 2 批", "开始 E1 第 1 批 "])
def test_nonmatching_terminal_text_is_not_accepted(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    terminal(monkeypatch, text)
    with pytest.raises(member_start.ManualStartRejected, match="不匹配"):
        member_start.confirm_local("E1", 1)


def test_noninteractive_cli_does_not_load_central_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("开始 E1 第 1 批\n"))
    monkeypatch.setattr(
        CentralLocation,
        "from_environment",
        lambda: pytest.fail("no PG before terminal approval"),
    )
    output = tmp_path / "receipt.json"
    assert (
        member_start.main(
            [
                "--suite",
                "E1",
                "--batch-number",
                "1",
                "--scenario",
                "T01",
                "--receipt",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()


def test_exact_terminal_confirmation_creates_only_one_short_lived_pg_grant(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    values = configure_central(p2_repo, monkeypatch)
    for key, name in ENVIRONMENT.items():
        monkeypatch.setenv(name, values[key])
    terminal(monkeypatch, "开始 E1 第 1 批")
    output = tmp_path / "receipt.json"
    assert (
        member_start.main(
            [
                "--suite",
                "E1",
                "--batch-number",
                "1",
                "--scenario",
                "T01",
                "--receipt",
                str(output),
            ]
        )
        == 0
    )
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["scenario_ids"] == ["T01"] and receipt["automatic_next_batch"] is False
    guard = QuotaGuard(**values)
    assert guard.status()["window"]["total"] == 0
    assert guard.status()["next_batch_not_before"] is None
    with guard.store.connect() as connection:
        batch = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE batch_id=%s").format(guard.store.table("core_model_batches")),
            (receipt["batch_id"],),
        ).fetchone()
    assert batch["authorization_id"] == receipt["authorization_id"]
    assert 899 <= (batch["expires_at"] - batch["started_at"]).total_seconds() <= 900


def test_receipt_write_failure_retains_pg_batch_without_reopening_or_posting(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = configure_central(p2_repo, monkeypatch)
    for key, name in ENVIRONMENT.items():
        monkeypatch.setenv(name, values[key])
    terminal(monkeypatch, "开始 E1 第 1 批")

    def fail_write(*_: object) -> None:
        raise OSError("private failure")

    monkeypatch.setattr(member_start, "write_private_receipt", fail_write)
    assert (
        member_start.main(
            [
                "--suite",
                "E1",
                "--batch-number",
                "1",
                "--scenario",
                "T01",
                "--receipt",
                str(tmp_path / "receipt.json"),
            ]
        )
        == 2
    )
    diagnostic = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert diagnostic["code"] == "GRANT_CREATED_RECEIPT_WRITE_FAILED"
    assert diagnostic["requires_manual_close_or_expiry"] is True
    guard = QuotaGuard(**values)
    with guard.store.connect() as connection:
        batches = connection.execute(
            sql.SQL("SELECT * FROM {}").format(guard.store.table("core_model_batches"))
        ).fetchall()
    assert len(batches) == 1 and batches[0]["batch_id"] == diagnostic["batch_id"]
    assert guard.status()["window"]["total"] == 0

"""CLI refuses remote/stage before connection and never prints connection secrets."""

from __future__ import annotations

import json
import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.tools import set_runtime
from mingjing_core.tools.runtime_switch_target import TargetError, local_target


@pytest.fixture(autouse=True)
def clean_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PGSERVICE", raising=False)
    monkeypatch.delenv("PGOPTIONS", raising=False)


@pytest.mark.parametrize(
    "dsn",
    [
        "",
        "host=example.com dbname=core_test user=core_test",
        "host=127.0.0.1 dbname=zhiming_core_live user=x",
        "host=127.0.0.1 dbname=zhiming_core_stage_test user=x",
        "host=127.0.0.1 dbname=normal user=x",
        "host=127.0.0.1 dbname=core_test",
        "host=127.0.0.1 hostaddr=8.8.8.8 dbname=core_test user=x",
        "host=127.0.0.1,example.com dbname=core_test user=x",
        "service=hidden dbname=core_test user=x",
        "host=/tmp dbname=core_test user=x",
        "host=127.0.0.1 dbname=core_test user=x options='-c x=y'",
        "host=127.0.0.1 dbname=core_test user=x port=0",
        "host=127.0.0.1 dbname=core_test user=x port=65536",
    ],
)
def test_unsafe_targets_rejected_before_repository(
    dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        set_runtime, "PostgresRepository", lambda *a, **k: pytest.fail("connected")
    )
    with pytest.raises(TargetError):
        local_target("local", dsn, "mingjing_core")
    monkeypatch.setenv("SYNTHETIC_RUNTIME_DSN", dsn)
    assert (
        set_runtime.main(
            [
                "--owner",
                "alice",
                "--runtime",
                "v4",
                "--dsn-env",
                "SYNTHETIC_RUNTIME_DSN",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["code"] == "target_or_arguments"


def test_localhost_is_pinned_and_cannot_use_inherited_pgpass() -> None:
    dsn, target = local_target(
        "local", "host=localhost dbname=core_test user=synthetic", "mingjing_core"
    )
    params = conninfo_to_dict(dsn)
    assert params["hostaddr"] == "127.0.0.1" and params["passfile"] == os.devnull
    assert params["port"] == "5432" and len(target) == 64


@pytest.mark.parametrize("name", ["PGSERVICE", "PGOPTIONS"])
def test_inherited_routing_is_rejected(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, "synthetic-private-value")
    with pytest.raises(TargetError):
        local_target("local", "host=127.0.0.1 dbname=core_test user=x", "mingjing_core")


def test_stage_is_explicitly_unsupported_before_connection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        set_runtime, "PostgresRepository", lambda *a, **k: pytest.fail("connected")
    )
    assert (
        set_runtime.main(
            ["--owner", "alice", "--runtime", "v4", "--environment", "stage"]
        )
        == 2
    )
    assert "stage 入口尚未启用" in json.loads(capsys.readouterr().out)["message"]


@pytest.mark.parametrize(
    "extra", [["--apply"], ["--expect-runtime", "v3"], ["--request-id", "preview-key"]]
)
def test_write_requires_complete_explicit_arguments_before_connection(
    extra: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        set_runtime, "PostgresRepository", lambda *a, **k: pytest.fail("connected")
    )
    assert set_runtime.main(["--owner", "alice", "--runtime", "v4", *extra]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "target_or_arguments"


def test_database_error_redacts_private_connection_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "SYNTHETIC_RUNTIME_DSN",
        "host=127.0.0.1 dbname=core_test user=x password=synthetic-key",
    )
    monkeypatch.setattr(
        set_runtime,
        "verify_target",
        lambda *args: (_ for _ in ()).throw(
            psycopg.OperationalError("password=synthetic-key postgresql://private-body")
        ),
    )
    assert (
        set_runtime.main(
            [
                "--owner",
                "alice",
                "--runtime",
                "v4",
                "--dsn-env",
                "SYNTHETIC_RUNTIME_DSN",
            ]
        )
        == 2
    )
    output = capsys.readouterr().out
    assert (
        "synthetic-key" not in output
        and "private-body" not in output
        and "postgresql://" not in output
    )
    assert json.loads(output)["code"] == "database"


def test_cli_dry_run_apply_replay_and_unknown_owner_real_pg(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SYNTHETIC_RUNTIME_DSN", p2_repo.dsn)
    common = [
        "--owner",
        "alice",
        "--runtime",
        "v4",
        "--dsn-env",
        "SYNTHETIC_RUNTIME_DSN",
        "--schema",
        p2_repo.schema,
    ]
    assert set_runtime.main(common) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["mode"] == "dry-run" and preview["old_runtime"] == "v3"
    assert "runtime" not in p2_repo.assert_scope("alice")["settings"]
    apply = [*common, "--apply", "--expect-runtime", "v3", "--request-id", "cli-switch"]
    assert set_runtime.main(apply) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["changed"] is True and len(receipt["owner_sha256"]) == 64
    assert set_runtime.main(apply) == 0
    assert json.loads(capsys.readouterr().out)["replayed"] is True
    common[1] = "unknown-owner"
    assert set_runtime.main(common) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "owner_scope"


def test_uninitialized_schema_is_not_created_by_cli(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SYNTHETIC_RUNTIME_DSN", p2_repo.dsn)
    schema = p2_repo.schema + "_absent"
    assert (
        set_runtime.main(
            [
                "--owner",
                "alice",
                "--runtime",
                "v4",
                "--schema",
                schema,
                "--dsn-env",
                "SYNTHETIC_RUNTIME_DSN",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["code"] == "invalid_state_or_replay"
    with p2_repo.transaction() as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,)
            ).fetchone()
            is None
        )

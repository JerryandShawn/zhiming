"""Read-only synthetic source dump, real PG restore and explicit no-adoption boundaries."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql
from test_first_release_local_restore_pg import pg_program
from test_first_release_native_exchange_pg import db_dsn
from test_first_release_native_exchange_pg import sample as sample_fixture  # noqa: F401

from tools.first_release_contracts import RestoreRejected
from tools.first_release_database_metadata import capture, semantic
from tools.first_release_native_exchange import control, file_hash
from tools.first_release_stage_copy import CopyScope, copy_stage, main


@pytest.fixture
def copied_source(tmp_path):
    yield from sample_fixture.__wrapped__(tmp_path)


def test_readonly_original_backup_and_new_closed_copy_preserve_owner_acl_settings_and_data(copied_source, tmp_path):
    sample = copied_source
    scope = CopyScope(sample.scope.operation, local_drill=True)
    workspace = tmp_path / "stage-copy"
    workspace.mkdir(mode=0o700)
    dump, restore = pg_program("pg_dump"), pg_program("pg_restore")
    result = copy_stage(
        scope, workspace, dump, restore, file_hash(dump), file_hash(restore), environment=sample.environment
    )
    assert result["status"] == "copied_closed" and result["source_readonly"] and not result["admission_opened"]
    assert (workspace / "original-stage.dump").is_file() and (workspace / "source-database-metadata.json").is_file()
    with control(scope, sample.environment) as (admin, _):
        assert capture(admin, scope.source) == sample.metadata
        assert semantic(capture(admin, scope.target)) == semantic(sample.metadata)
        assert not admin.execute("SELECT datallowconn FROM pg_database WHERE datname=%s", (scope.target,)).fetchone()[
            "datallowconn"
        ]
        admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(scope.target)))
    for name in (scope.source, scope.target):
        with psycopg.connect(db_dsn(sample, name)) as connection:
            assert connection.execute("SELECT body FROM synthetic.core_runs").fetchone() == (
                "SYNTHETIC_PRIVATE_ORIGINAL",
            )
    rejected = tmp_path / "must-not-adopt"
    rejected.mkdir(mode=0o700)
    with pytest.raises(RestoreRejected):
        copy_stage(scope, rejected, dump, restore, file_hash(dump), file_hash(restore), environment=sample.environment)
    assert list(rejected.iterdir()) == []


def test_copy_default_validates_without_reading_credentials_opening_pg_or_writing(monkeypatch, tmp_path, capsys):
    import tools.first_release_stage_copy as module

    def deny(*args, **kwargs):
        pytest.fail("default validation must not connect or create backup")

    monkeypatch.setattr(module, "control", deny)
    assert (
        main(
            [
                "--operation",
                "a" * 16,
                "--workspace",
                str(tmp_path),
                "--pg-dump",
                str(tmp_path / "absent"),
                "--pg-dump-sha256",
                "b" * 64,
                "--pg-restore",
                str(tmp_path / "absent"),
                "--pg-restore-sha256",
                "c" * 64,
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == [] and '"database_connections": 0' in capsys.readouterr().out

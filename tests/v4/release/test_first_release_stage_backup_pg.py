"""Real empty-delta prefix8 archive/restore/exchange and retained-client rejection."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_first_release_local_restore_pg import pg_program
from test_first_release_native_exchange_pg import db_dsn, set_closed
from test_first_release_native_exchange_pg import sample as sample_fixture  # noqa: F401
from test_first_release_stage_prepare_pg import seed_prefix_four

from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.runtime import LangGraphRuntime
from tools.first_release_contracts import RestoreRejected
from tools.first_release_database_metadata import capture, semantic
from tools.first_release_native_exchange import control, exchange, file_hash, restore_new, seal
from tools.first_release_replay_effects import snapshot
from tools.first_release_stage_backup import backup_closed


@pytest.fixture
def empty_stage(tmp_path):
    yield from sample_fixture.__wrapped__(tmp_path)


def repo_for(sample, database):
    return PostgresRepository(
        make_conninfo(
            db_dsn(sample, database), options="-c role=" + sample.owner + " -c search_path=public,pg_catalog"
        ),
        initialize=False,
        max_size=2,
    )


def test_empty_delta_prefix8_native_restore_exchange_retains_both_databases(empty_stage, tmp_path):
    sample = empty_stage
    seed_prefix_four(sample)
    repo = repo_for(sample, sample.scope.original)
    try:
        repo.initialize()
        LangGraphRuntime(repo)
        before = snapshot(repo)
    finally:
        repo.close()
    set_closed(sample, sample.scope.original)
    workspace = tmp_path / "empty-delta"
    workspace.mkdir(mode=0o700)
    dump, restore = pg_program("pg_dump"), pg_program("pg_restore")
    receipt = backup_closed(
        sample.scope, workspace, sample.metadata, dump, file_hash(dump), environment=sample.environment
    )
    restored = restore_new(
        sample.scope,
        sample.metadata,
        workspace / "empty-delta.dump",
        receipt["backup_sha256"],
        restore,
        file_hash(restore),
        environment=sample.environment,
    )
    seal(sample.scope, sample.metadata, environment=sample.environment)
    result = exchange(sample.scope, sample.metadata, restored, environment=sample.environment)
    assert result["admission_opened"] is result["old_database_deleted"] is False
    with control(sample.scope, sample.environment) as (admin, _):
        current, failed = capture(admin, sample.scope.original), capture(admin, sample.scope.failed)
        assert current["oid"] == restored["replacement_oid"] and failed["oid"] == sample.metadata["oid"]
        assert semantic(current) == semantic(failed) == semantic(sample.metadata)
        assert (
            admin.execute(
                "SELECT datallowconn FROM pg_database WHERE oid=ANY(%s)", ([current["oid"], failed["oid"]],)
            ).fetchall()
            == [{"datallowconn": False}] * 2
        )
        for name in (sample.scope.original, sample.scope.failed):
            # Test-only read access after asserting the actual exchange kept both closed.
            admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(name)))
    for name in (sample.scope.original, sample.scope.failed):
        repo = repo_for(sample, name)
        try:
            assert snapshot(repo) == before
            repo.verify_schema()
        finally:
            repo.close()


def test_backup_rejects_inflight_client_without_changing_or_terminating_it(empty_stage, tmp_path):
    sample = empty_stage
    workspace = tmp_path / "rejected"
    workspace.mkdir(mode=0o700)
    with psycopg.connect(db_dsn(sample, sample.scope.original), autocommit=True) as client:
        set_closed(sample, sample.scope.original)
        program = pg_program("pg_dump")
        with pytest.raises(RestoreRejected, match="STAGE_BACKUP_CLOSED_ZERO_REQUIRED"):
            backup_closed(
                sample.scope, workspace, sample.metadata, program, file_hash(program), environment=sample.environment
            )
        assert client.execute("SELECT 1").fetchone() == (1,)
    assert not (workspace / "empty-delta-started.json").exists()
    assert not (workspace / "empty-delta.dump").exists()


def test_backup_refuses_old_prefix_before_creating_archive_and_preserves_started_marker(empty_stage, tmp_path):
    sample = empty_stage
    seed_prefix_four(sample)
    set_closed(sample, sample.scope.original)
    workspace = tmp_path / "old-prefix"
    workspace.mkdir(mode=0o700)
    program = pg_program("pg_dump")
    with pytest.raises(RestoreRejected, match="STAGE_BACKUP_PREFIX8_CHECKPOINT_REQUIRED"):
        backup_closed(
            sample.scope, workspace, sample.metadata, program, file_hash(program), environment=sample.environment
        )
    assert (workspace / "empty-delta-started.json").exists()
    assert not (workspace / "empty-delta.dump").exists()
    with psycopg.connect(db_dsn(sample, sample.scope.original)) as connection:
        assert connection.execute("SELECT max(version) FROM mingjing_core.schema_migrations").fetchone() == (4,)

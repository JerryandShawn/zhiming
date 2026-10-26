"""Actual old-prefix copy migration, primary backfill and retained receipt replay without source writes."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from test_first_release_local_restore_pg import pg_program
from test_first_release_native_exchange_pg import db_dsn
from test_first_release_native_exchange_pg import sample as sample_fixture  # noqa: F401

from mingjing_core.repositories.foundation import migration_manifest
from tools.first_release_contracts import RestoreRejected
from tools.first_release_database_metadata import capture
from tools.first_release_native_exchange import control, file_hash
from tools.first_release_stage_copy import CopyScope, copy_stage
from tools.first_release_stage_prepare import main, prepare_copy


@pytest.fixture
def old_stage(tmp_path):
    yield from sample_fixture.__wrapped__(tmp_path)


def seed_prefix_four(sample):
    root = Path(__file__).resolve().parents[3] / "mingjing_core/repositories/migrations"
    expected = migration_manifest()
    with psycopg.connect(db_dsn(sample, sample.scope.original)) as connection:
        connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(sample.owner)))
        connection.execute("CREATE SCHEMA mingjing_core")
        connection.execute("SET LOCAL search_path=mingjing_core")
        connection.execute("CREATE TABLE schema_migrations(version integer PRIMARY KEY,checksum text)")
        for path in sorted(root.glob("000[1-4]_*.sql")):
            connection.execute(path.read_text(encoding="utf-8"))
            version = int(path.name[:4])
            connection.execute(
                "INSERT INTO schema_migrations VALUES(%s,%s)",
                (version, expected[version]),
            )
        connection.execute("INSERT INTO core_owners(id) VALUES('primary')")
        connection.execute("INSERT INTO core_subjects VALUES('primary','self','SYNTHETIC','granted')")
        connection.execute(
            "INSERT INTO core_entities(owner,kind,id,subject,data) VALUES"
            "('primary','message','msg-before','self',"
            '\'{"role":"user","content":"SYNTHETIC_LEGACY_MESSAGE","at":"2026-10-20T00:00:00Z"}\')'
        )
        connection.execute(
            "INSERT INTO delivery_outbox(id,owner,subject,business_id,channel,target,run_id,status,due,receipt) VALUES"
            "('sent-before','primary','self','biz-before','web','synthetic','run-before',"
            "'sent',now(),'SYNTHETIC_RECEIPT')"
        )


def test_old_copy_forward_backfill_replay_closed_and_source_untouched(old_stage, tmp_path):
    sample = old_stage
    seed_prefix_four(sample)
    scope = CopyScope(sample.scope.operation, local_drill=True)
    workspace = tmp_path / "prepare"
    workspace.mkdir(mode=0o700)
    dump, restore = pg_program("pg_dump"), pg_program("pg_restore")
    copied = copy_stage(
        scope,
        workspace,
        dump,
        restore,
        file_hash(dump),
        file_hash(restore),
        environment=sample.environment,
    )
    with pytest.raises(RestoreRejected, match="STAGE_COPY_IDENTITY_CHANGED"):
        prepare_copy(
            scope,
            workspace,
            dict(copied, target_oid=copied["target_oid"] + 1),
            environment=sample.environment,
        )
    assert not (workspace / "prepare-started.json").exists()
    result = prepare_copy(scope, workspace, copied, environment=sample.environment)
    assert result["status"] == "prepared_closed" and not result["admission_opened"]
    assert result["migrations_applied"] == [5, 6, 7, 8]
    assert result["backfill_apply"]["message_metadata"] == 1 and result["backfill_apply"]["search_tokens"] == 1
    assert result["backfill_repeat"]["message_metadata"] == result["backfill_repeat"]["search_tokens"] == 0
    assert result["backfill_repeat"]["assistant_created"] == 0 and result["replay_full_state_unchanged"]
    # Existing sent receipts are preserved without another write; this counter reports updates.
    assert result["replay"]["protected_receipts"] == result["replay_repeat"]["protected_receipts"] == 0
    with control(scope, sample.environment) as (admin, _):
        assert capture(admin, scope.source) == sample.metadata
        row = admin.execute("SELECT datallowconn FROM pg_database WHERE datname=%s", (scope.target,)).fetchone()
        assert not row["datallowconn"]
        admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(scope.target)))
    with psycopg.connect(db_dsn(sample, scope.source)) as source:
        assert source.execute("SELECT max(version) FROM mingjing_core.schema_migrations").fetchone() == (4,)
        assert source.execute("SELECT data ? 'search_tokens' FROM mingjing_core.core_entities").fetchone() == (False,)
    with psycopg.connect(db_dsn(sample, scope.target)) as target:
        assert target.execute("SELECT max(version) FROM mingjing_core.schema_migrations").fetchone() == (8,)
        assert target.execute("SELECT status,receipt FROM mingjing_core.delivery_outbox").fetchone() == (
            "sent",
            "SYNTHETIC_RECEIPT",
        )
        assert target.execute(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='mingjing_core.core_run_events'::regclass"
        ).fetchone() == (sample.owner,)
    with pytest.raises(RestoreRejected, match="STAGE_PREPARE_ALREADY_STARTED_NO_RETRY"):
        prepare_copy(scope, workspace, copied, environment=sample.environment)


def test_default_prepare_does_not_load_receipt_or_credentials_or_connect(monkeypatch, tmp_path, capsys):
    import tools.first_release_stage_prepare as module

    def deny(*args, **kwargs):
        pytest.fail("validate-only must not consume private files or connect")

    monkeypatch.setattr(module, "prepare_copy", deny)
    monkeypatch.setattr(module, "file_hash", deny)
    assert (
        main(
            [
                "--operation",
                "a" * 16,
                "--workspace",
                str(tmp_path),
                "--copy-receipt",
                str(tmp_path / "missing"),
                "--copy-receipt-sha256",
                "b" * 64,
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == [] and '"database_connections": 0' in capsys.readouterr().out

"""Actual restore then pinned forward migration; failures never adopt or repair old targets."""

from __future__ import annotations

import json

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from test_first_release_local_restore_pg import PRIVATE
from test_first_release_local_restore_pg import sample as sample

from tools import first_release_local_restore, first_release_local_upgrade
from tools.first_release_acl import QUOTA
from tools.first_release_contracts import RestoreRejected
from tools.first_release_local_restore import execute


def snapshot(dsn):
    with psycopg.connect(dsn) as connection:
        result = {
            "entities": connection.execute(
                "SELECT owner,kind,id,subject,case_id,data,status,revision,created_at,updated_at "
                "FROM mingjing_core.core_entities ORDER BY owner,kind,id"
            ).fetchall()
        }
        for table in ("checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            result[table] = connection.execute(
                sql.SQL("SELECT * FROM public.{} ORDER BY 1,2").format(sql.Identifier(table))
                if table != "checkpoint_migrations"
                else "SELECT * FROM public.checkpoint_migrations ORDER BY v"
            ).fetchall()
    return result


def seed_checkpoints(sample):
    with psycopg.connect(sample.source) as connection:
        connection.execute(
            "INSERT INTO public.checkpoints(thread_id,checkpoint_ns,checkpoint_id,checkpoint,metadata) "
            "VALUES('synthetic-run:e0','','synthetic-checkpoint',%s,%s)",
            (Jsonb({"v": 1, "id": "synthetic-checkpoint"}), Jsonb({"source": "synthetic"})),
        )
        connection.execute(
            "INSERT INTO public.checkpoint_blobs(thread_id,checkpoint_ns,channel,version,type,blob) "
            "VALUES('synthetic-run:e0','','synthetic-channel','1','bytes',%s)",
            (b"synthetic-checkpoint-blob",),
        )
        connection.execute(
            "INSERT INTO public.checkpoint_writes(thread_id,checkpoint_ns,checkpoint_id,task_id,idx,channel,type,blob) "
            "VALUES('synthetic-run:e0','','synthetic-checkpoint','synthetic-task',0,'synthetic-channel','bytes',%s)",
            (b"synthetic-checkpoint-write",),
        )
    sample.dump()


def retained(sample, version):
    assert sample.present() == (True, 2), "FAILED_LOCAL_TARGET_MUST_BE_RETAINED"
    with psycopg.connect(sample.environment["FIRST_RELEASE_OWNER_DSN"]) as connection:
        rows = connection.execute("SELECT version FROM mingjing_core.schema_migrations ORDER BY version").fetchall()
        assert [row[0] for row in rows] == list(range(1, version + 1)), "UNEXPECTED_RETAINED_PHASE"


def quota_counts(sample):
    with psycopg.connect(sample.environment["FIRST_RELEASE_OWNER_DSN"]) as connection:
        return [
            connection.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(*table.split(".")))).fetchone()[
                0
            ]
            for table in QUOTA
        ]


@pytest.mark.parametrize("sample", [4, 7], indirect=True)
def test_actual_fresh_restore_upgrades_to8_preserving_data_and_checkpoint_with_exact_acl(sample):
    seed_checkpoints(sample)
    before = snapshot(sample.source)
    result = execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
    assert result["local_upgrade_completed"] is result["runtime_acl_verified"] is True
    assert result["database_connections"] == 7 and result["acl"]["database_connections"] == 2
    assert result["forward_migrations"] == list(range(len(sample.inputs.dump_pin.source_migrations) + 1, 9))
    assert result["original_prefix"] == dict(sample.inputs.dump_pin.source_migrations)
    assert result["upgraded_migrations"] == dict(sample.inputs.release.migrations)
    assert result["central_ledger_empty"] is True and quota_counts(sample) == [0, 0, 0, 0]
    assert result["central_binding_verified"] is result["central_provisioned"] is False
    assert result["latest_withdrawals_replayed"] is result["native_restore_completed"] is False
    assert result["linux_attestation"] is result["publication"] is result["runtime_verified"] is False
    assert PRIVATE not in json.dumps(result), "UPGRADE_RECEIPT_MUST_NOT_CONTAIN_BODY"
    assert snapshot(sample.environment["FIRST_RELEASE_OWNER_DSN"]) == before, "ORIGINAL_OR_CHECKPOINT_CHANGED"
    assert result["acl"]["quota_tables_checked"] == 4
    with psycopg.connect(sample.environment["FIRST_RELEASE_WRITER_DSN"]) as writer:
        for table, allowed in QUOTA.items():
            for right in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                actual = writer.execute("SELECT has_table_privilege(current_user,%s,%s)", (table, right)).fetchone()[0]
                assert actual == (right in allowed), "EXACT_QUOTA_RIGHT_REQUIRED"
    with pytest.raises(RestoreRejected, match="ALREADY_EXISTS"):
        execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
    assert snapshot(sample.environment["FIRST_RELEASE_OWNER_DSN"]) == before, "EXISTING_TARGET_WAS_REUSED"


def test_upgrade_flag_without_same_call_apply_never_connects_or_executes(sample, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("UPGRADE_WITHOUT_APPLY_MUST_NOT_CONNECT_OR_SPAWN")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(first_release_local_restore.subprocess, "run", forbidden)
    with pytest.raises(RestoreRejected, match="LOCAL_UPGRADE_REQUIRES_APPLY"):
        execute(sample.inputs, upgrade_local=True, environment=sample.environment)


def test_migration_sql_error_rolls_back_whole_forward_transaction_and_keeps_original(sample):
    with psycopg.connect(sample.source) as connection:
        connection.execute("ALTER TABLE mingjing_core.core_runs ADD COLUMN kind text")
    sample.dump()
    with pytest.raises(RestoreRejected, match="LOCAL_UPGRADE_CORE_TRANSACTION_FAILED"):
        execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
    retained(sample, 4)
    with psycopg.connect(sample.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
        assert owner.execute("SELECT to_regclass('mingjing_core.core_model_accounts') IS NULL").fetchone() == (True,)
        assert owner.execute("SELECT to_regclass('mingjing_core.core_run_steps') IS NULL").fetchone() == (True,)
    with pytest.raises(RestoreRejected, match="ALREADY_EXISTS"):
        execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)


def after_original(monkeypatch, change):
    original = first_release_local_restore.verify_original

    def changed(inputs, owner_dsn):
        result = original(inputs, owner_dsn)
        change(inputs, owner_dsn)
        return result

    monkeypatch.setattr(first_release_local_restore, "verify_original", changed)


def test_changed_reviewed_sql_after_restore_is_refused_before_forward_migration(sample, monkeypatch):
    def change(inputs, owner_dsn):
        path = next((inputs.contract.candidate_source / first_release_local_upgrade.MIGRATION_DIR).glob("0008_*.sql"))
        path.write_bytes(path.read_bytes() + b"\n-- changed after original restore\n")

    after_original(monkeypatch, change)
    with pytest.raises(RestoreRejected, match="SOURCE_MEMBER_CHANGED"):
        execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
    retained(sample, 4)


def test_changed_historical_checksum_after_restore_stops_without_adopting_it(sample, monkeypatch):
    def change(inputs, owner_dsn):
        with psycopg.connect(owner_dsn) as owner:
            owner.execute("UPDATE mingjing_core.schema_migrations SET checksum=%s WHERE version=4", ("b" * 64,))

    after_original(monkeypatch, change)
    with pytest.raises(RestoreRejected, match="LOCAL_UPGRADE_HISTORY_REJECTED"):
        execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
    retained(sample, 4)


def test_actual_checkpoint_failure_keeps_committed_core8_without_grants_or_retry(sample):
    with psycopg.connect(sample.source) as connection:
        connection.execute("ALTER TABLE public.checkpoint_migrations RENAME COLUMN v TO unreviewed_v")
    sample.dump()
    with pytest.raises(RestoreRejected, match="LOCAL_UPGRADE_CHECKPOINT_FAILED"):
        execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
    retained(sample, 8)
    assert quota_counts(sample) == [0, 0, 0, 0]
    with psycopg.connect(sample.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
        assert owner.execute("SELECT count(*) FROM public.checkpoint_migrations").fetchone()[0] > 0


def test_extra_quota_delete_permission_fails_final_acl_without_automatic_repair(sample, monkeypatch):
    original = first_release_local_upgrade.grant_runtime_tables

    def excessive(connection, writer, *args, **kwargs):
        result = original(connection, writer, *args, **kwargs)
        connection.execute(
            sql.SQL("GRANT DELETE ON mingjing_core.core_model_authorizations TO {}").format(sql.Identifier(writer))
        )
        return result

    monkeypatch.setattr(first_release_local_upgrade, "grant_runtime_tables", excessive)
    with pytest.raises(RestoreRejected, match="LOCAL_UPGRADE_ACL_REJECTED"):
        execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
    retained(sample, 8)
    assert quota_counts(sample) == [0, 0, 0, 0]
    with psycopg.connect(sample.environment["FIRST_RELEASE_WRITER_DSN"]) as writer:
        assert writer.execute(
            "SELECT has_table_privilege(current_user,'mingjing_core.core_model_authorizations','DELETE')"
        ).fetchone() == (True,)


def test_nonempty_central_table_stops_and_never_deletes_or_reprovisions_it(sample, monkeypatch):
    original = first_release_local_upgrade.PostgresSaver.setup

    def occupied(saver):
        original(saver)
        saver.conn.execute(
            "INSERT INTO mingjing_core.core_model_accounts(account_id,ledger_identity,location_id) "
            "VALUES('synthetic-unexpected-account','00000000-0000-0000-0000-000000000001',%s)",
            ("a" * 64,),
        )

    monkeypatch.setattr(first_release_local_upgrade.PostgresSaver, "setup", occupied)
    with pytest.raises(RestoreRejected, match="LOCAL_UPGRADE_CENTRAL_TABLE_NOT_EMPTY"):
        execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
    retained(sample, 8)
    assert quota_counts(sample) == [1, 0, 0, 0], "UNEXPECTED_LEDGER_MUST_NOT_BE_CLEARED"


def test_internal_upgrade_refuses_an_ordinary_admin_session_without_fresh_creator_lock(sample):
    dsns = sample.inputs.connections(sample.environment)
    with psycopg.connect(dsns["admin"], autocommit=True, row_factory=dict_row) as admin:
        admin.execute("SET search_path=pg_catalog")
        with pytest.raises(RestoreRejected, match="LOCAL_UPGRADE_FRESH_CREATOR_LOCK_REQUIRED"):
            first_release_local_upgrade._upgrade_new_target(sample.inputs, dsns, admin)
    assert sample.present() == (False, 0), "UNLOCKED_ADMIN_MUST_NOT_ADOPT_A_TARGET"

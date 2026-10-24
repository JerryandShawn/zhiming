"""Admission closes real native writer entry, then one strict M1 capture adopts its retained marker."""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from first_release_service_process_support import BODY, service_child
from first_release_support import ROOT
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_first_release_incremental_backup_pg import archive as source_archive
from test_first_release_incremental_backup_pg import existing as source_fixture
from test_first_release_incremental_backup_pg import state

from mingjing_core.repositories.permissions import grant_runtime_tables
from tools import first_release_incremental_pg as pg
from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental import execute
from tools.first_release_incremental_guard import file_stamp, maintenance_material
from tools.first_release_writer_fence import pg_lock

OUTPUTS = ("backup-started.json", "latest-withdrawals.json", "backup.dump", "backup-receipt.json")


@pytest.fixture(scope="module")
def archive():
    return source_archive.__wrapped__()


def grant_test_writer(existing):
    source = existing.inputs.source
    writer = source.database + "_writer"
    with psycopg.connect(existing.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
        granted = grant_runtime_tables(owner, writer)
        assert granted == ["core_run_steps", "core_run_events", "core_embeddings"]
        assert owner.execute("SELECT to_regclass('mingjing_core.core_model_accounts')").fetchone() == (None,)
    with psycopg.connect(make_conninfo(existing.admin, dbname=source.database)) as admin:
        before = admin.execute(
            "SELECT has_function_privilege(%s,'pg_catalog.pg_control_system()','EXECUTE')", (writer,)
        ).fetchone()[0]
        if not before:
            admin.execute(
                sql.SQL("GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO {}").format(sql.Identifier(writer))
            )
    return before


@pytest.fixture
def source(archive):
    with contextmanager(source_fixture.__wrapped__)(SimpleNamespace(param=7), archive) as existing:
        sid_before = grant_test_writer(existing)
        inputs, identity = existing.inputs, existing.inputs.source
        inputs.fence_path.parent.mkdir(parents=True)
        inputs.fence_path.write_bytes(b"synthetic-existing-admission-fence")
        values = {
            "role": "report",
            "candidate": ROOT,
            "workspace": inputs.workspace,
            "system-identifier": identity.system_identifier,
            "database": identity.database,
            "database-oid": identity.database_oid,
            "writer": identity.database + "_writer",
            "writer-oid": identity.writer_oid,
        }
        yield SimpleNamespace(
            existing=existing,
            inputs=inputs,
            environment=existing.environment,
            writer_dsn=existing.environment["FIRST_INCREMENTAL_WRITER_DSN"],
            arguments=[item for key, value in values.items() for item in ("--" + key, str(value))],
            source="admission-" + uuid.uuid4().hex,
            sid_execute_preexisting=sid_before,
        )


def close(source):
    return execute(source.inputs, close_admission_local=True, environment=source.environment)


def adopt(source):
    return execute(source.inputs, backup_local=True, use_admission=True, environment=source.environment)


def no_outputs(source):
    assert not any((source.inputs.operation_dir / name).exists() for name in OUTPUTS)


def rejected_child(source):
    with service_child(source) as child:
        stdout, stderr = child.finish(2)
    assert stdout == "" and stderr == "SERVICE_CONFIGURATION_OR_FENCE_REJECTED\n"


def writer_commits(source):
    with psycopg.connect(source.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
        rows = owner.execute(
            "SELECT data FROM mingjing_core.core_entities WHERE owner='synthetic' AND kind='message' "
            "AND data->>'source_id'=ANY(%s)",
            ([source.source + "-main", source.source + "-background"],),
        ).fetchall()
    assert len(rows) == 2 and all(row[0]["content"] == BODY for row in rows)


def wait_pg_release(source):
    deadline = time.monotonic() + 3
    while True:
        try:
            with (
                psycopg.connect(
                    source.environment["FIRST_INCREMENTAL_OWNER_DSN"],
                    autocommit=True,
                    row_factory=psycopg.rows.dict_row,
                ) as owner,
                pg_lock(owner, source.inputs.fence_key, exclusive=True),
            ):
                return
        except RestoreRejected as error:
            assert str(error) == "INCREMENTAL_PG_FENCE_BUSY"
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def test_live_native_writer_can_close_admission_then_original_marker_is_adopted_by_real_m1(source, record_property):
    with service_child(source) as child:
        child.state("native_ready")
        writer_commits(source)
        before = state(source.existing)
        result = close(source)
        assert result["admission_closed"] is True and result["global_quiescence_verified"] is False
        assert child.process.poll() is None
        marker = file_stamp(source.inputs.maintenance)
        marker_bytes = source.inputs.maintenance.read_bytes()
        assert json.loads(marker_bytes) == {
            "operation_id": source.inputs.operation_id,
            "database_oid": source.inputs.source.database_oid,
        }
        rejected_child(source)
        assert state(source.existing) == before and file_stamp(source.inputs.maintenance) == marker
        child.send("return")
        child.state("native_finished")
        child.send("exit")
        stdout, stderr = child.finish(0)
        assert len(stdout.splitlines()) == 2 and stderr == ""
    wait_pg_release(source)
    captured = adopt(source)
    assert captured["backup_captured"] is captured["same_mvcc_snapshot"] is True
    assert captured["global_quiescence_verified"] is captured["source_upgraded"] is captured["publication"] is False
    assert state(source.existing) == before and file_stamp(source.inputs.maintenance) == marker
    assert source.inputs.maintenance.read_bytes() == marker_bytes
    materials = maintenance_material(source.inputs)
    assert len(materials) == 3 and all((source.inputs.operation_dir / name).is_file() for name in OUTPUTS)
    assert (source.inputs.operation_dir / "backup.dump").read_bytes()[:5] == b"PGDMP"
    ledger = json.loads((source.inputs.operation_dir / "latest-withdrawals.json").read_bytes())
    assert ledger["owners"][0]["revocations"][0]["entity_id"] == "synthetic-old"
    record_property("actual_native_writer_commits", 2)
    record_property("test_only_writer_runtime_grant", True)
    record_property("sid_execute_preexisting", source.sid_execute_preexisting)
    record_property("actual_external_requests", 0)


def default_no_io(source, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("DEFAULT_ADMISSION_MUST_NOT_CONNECT_SPAWN_OR_WRITE")

    with monkeypatch.context() as patch:
        for target, name in (
            (psycopg, "connect"),
            (subprocess, "Popen"),
            (subprocess, "run"),
            (os, "open"),
            (Path, "write_bytes"),
            (Path, "write_text"),
            (Path, "mkdir"),
        ):
            patch.setattr(target, name, forbidden)
        result = execute(source.inputs)
        assert result["database_connections"] == result["processes"] == result["file_writes"] == 0


def stable_marker_refuses_actual_timestamp_drift(source, monkeypatch):
    original, touched = pg.source_scope, []

    def drift(connection, inputs):
        original(connection, inputs)
        stamp = inputs.maintenance.stat()
        os.utime(inputs.maintenance, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000))
        touched.append(True)

    with monkeypatch.context() as patch:
        patch.setattr(pg, "source_scope", drift)
        with pytest.raises(RestoreRejected, match="ADMISSION_.*CHANGED"):
            adopt(source)
    assert touched == [True]
    no_outputs(source)


def test_default_identity_marker_protocol_and_actual_stability_fail_closed_without_core_changes(source, monkeypatch):
    before = state(source.existing)
    default_no_io(source, monkeypatch)
    wrong = replace(
        source.inputs, source=replace(source.inputs.source, database_oid=source.inputs.source.database_oid + 1)
    )
    wrong.fence_path.write_bytes(b"synthetic-wrong-oid-fence")
    with pytest.raises(RestoreRejected, match="^INCREMENTAL_ACTUAL_SOURCE_IDENTITY$"):
        execute(wrong, close_admission_local=True, environment=source.environment)
    assert not source.inputs.maintenance.exists() and state(source.existing) == before
    close(source)
    marker_bytes = source.inputs.maintenance.read_bytes()
    with pytest.raises(RestoreRejected, match="^INCREMENTAL_MAINTENANCE_ALREADY_PRESENT$"):
        execute(source.inputs, backup_local=True, environment=source.environment)
    stable_marker_refuses_actual_timestamp_drift(source, monkeypatch)
    assert source.inputs.maintenance.read_bytes() == marker_bytes
    for content in (
        json.dumps({"operation_id": "fr-" + "b" * 32, "database_oid": source.inputs.source.database_oid}).encode(),
        b"not-json",
    ):
        source.inputs.maintenance.write_bytes(content)
        with pytest.raises(RestoreRejected, match="ADMISSION_.*"):
            adopt(source)
        assert source.inputs.maintenance.read_bytes() == content
        assert state(source.existing) == before
        no_outputs(source)


def test_true_pg_dump_error_retains_closed_admission_partial_outputs_and_refuses_reentry(
    source, monkeypatch, record_property
):
    before = state(source.existing)
    close(source)
    marker = file_stamp(source.inputs.maintenance)
    original_dump, original_run, actual_codes = pg.dump, subprocess.run, []

    def failing_snapshot(inputs, dsn, snapshot_id):
        return original_dump(inputs, dsn, "00000000-00000000-0")

    def observed_run(command, *args, **kwargs):
        result = original_run(command, *args, **kwargs)
        if "--format=custom" in command:
            actual_codes.append(result.returncode)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(pg, "dump", failing_snapshot)
        patch.setattr(subprocess, "run", observed_run)
        with pytest.raises(RestoreRejected, match="^INCREMENTAL_PG_DUMP_FAILED_OUTPUT_RETAINED$"):
            adopt(source)
    assert len(actual_codes) == 1 and actual_codes[0] != 0
    assert file_stamp(source.inputs.maintenance) == marker and state(source.existing) == before
    retained = {name: (source.inputs.operation_dir / name).read_bytes() for name in OUTPUTS[:-1]}
    assert not (source.inputs.operation_dir / "backup-receipt.json").exists()
    assert json.loads(retained["backup-started.json"])["operation_id"] == source.inputs.operation_id
    assert json.loads(retained["latest-withdrawals.json"])["owners"][0]["revocations"]
    rejected_child(source)
    with pytest.raises(RestoreRejected, match="^INCREMENTAL_EXISTING_OUTPUT_REJECTED$"):
        adopt(source)
    assert state(source.existing) == before and file_stamp(source.inputs.maintenance) == marker
    assert retained == {name: (source.inputs.operation_dir / name).read_bytes() for name in OUTPUTS[:-1]}
    record_property("actual_pg_dump_error_count", 1)
    record_property("automatic_cleanup_or_retry", False)

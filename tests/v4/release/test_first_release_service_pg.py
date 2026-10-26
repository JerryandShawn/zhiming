"""Native dispatch/flush coordination only; actual writer, PG/OS locks and os._exit are never replaced."""

from __future__ import annotations

import builtins
import json
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from first_release_service_process_support import BODY, PRIVATE_ERROR, service_child
from first_release_support import ROOT
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_first_release_local_restore_pg import sample as local_restore_sample

from tools import first_release_service as launcher
from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental_pg import snapshot
from tools.first_release_local_restore import execute
from tools.first_release_service_binding import ServiceBinding
from tools.first_release_writer_fence import file_lock, pg_lock


@pytest.fixture(scope="module")
def restored(tmp_path_factory):
    with contextmanager(local_restore_sample.__wrapped__)(SimpleNamespace(param=7), tmp_path_factory) as sample:
        result = execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
        assert result["local_upgrade_completed"] is result["runtime_acl_verified"] is True
        assert result["native_restore_completed"] is result["linux_attestation"] is result["publication"] is False
        database, writer = sample.inputs.contract.database, sample.inputs.contract.database + "_writer"
        admin_dsn = make_conninfo(sample.admin, dbname=database)
        with psycopg.connect(admin_dsn, row_factory=dict_row) as admin:
            actual = admin.execute(
                "SELECT system_identifier::text AS sid,"
                "(SELECT oid FROM pg_database WHERE datname=current_database()) AS database_oid,"
                "(SELECT oid FROM pg_roles WHERE rolname=%s) AS writer_oid,"
                "has_function_privilege(%s,'pg_catalog.pg_control_system()','EXECUTE') AS sid_execute_preexisting "
                "FROM pg_catalog.pg_control_system()",
                (writer, writer),
            ).fetchone()
            if not actual["sid_execute_preexisting"]:
                admin.execute(
                    sql.SQL("GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO {}").format(
                        sql.Identifier(writer)
                    )
                )
        yield SimpleNamespace(sample=sample, actual=actual, admin_dsn=admin_dsn)


@pytest.fixture
def bound(restored, tmp_path):
    sample, actual = restored.sample, restored.actual
    binding = ServiceBinding(
        "report",
        ROOT,
        tmp_path,
        actual["sid"],
        sample.inputs.contract.database,
        actual["database_oid"],
        sample.inputs.contract.database + "_writer",
        actual["writer_oid"],
    )
    binding.fence_path.parent.mkdir(parents=True)
    binding.fence_path.write_bytes(b"synthetic-existing-fence")
    values = {
        "role": binding.role,
        "candidate": ROOT,
        "workspace": tmp_path,
        "system-identifier": binding.system_identifier,
        "database": binding.database,
        "database-oid": binding.database_oid,
        "writer": binding.writer,
        "writer-oid": binding.writer_oid,
    }
    return SimpleNamespace(
        binding=binding,
        arguments=[item for key, value in values.items() for item in ("--" + key, str(value))],
        writer_dsn=sample.environment["FIRST_RELEASE_WRITER_DSN"],
        owner_dsn=sample.environment["FIRST_RELEASE_OWNER_DSN"],
        admin_dsn=restored.admin_dsn,
        source="service-" + uuid.uuid4().hex,
        actual=actual,
    )


def source_state(bound):
    with psycopg.connect(bound.owner_dsn, row_factory=dict_row) as owner:
        owner.execute("SET TRANSACTION READ ONLY")
        return snapshot(owner)


def commits(bound):
    with psycopg.connect(bound.owner_dsn, row_factory=dict_row) as owner:
        rows = owner.execute(
            "SELECT data FROM mingjing_core.core_entities WHERE owner='synthetic' AND kind='message' "
            "AND data->>'source_id'=ANY(%s)",
            ([bound.source + "-main", bound.source + "-background"],),
        ).fetchall()
    assert len(rows) == 2 and all(row["data"]["content"] == BODY for row in rows)


def file_exclusive(bound, *, busy):
    if busy:
        with (
            pytest.raises(RestoreRejected, match="^INCREMENTAL_FILE_FENCE_BUSY$"),
            file_lock(bound.binding.fence_path, exclusive=True, existing_only=True),
        ):
            pytest.fail("shared service OS lock unexpectedly released")
    else:
        with file_lock(bound.binding.fence_path, exclusive=True, existing_only=True):
            assert bound.binding.fence_path.is_file()


def pg_exclusive(bound, *, busy):
    with psycopg.connect(bound.owner_dsn, autocommit=True, row_factory=dict_row) as owner:
        if busy:
            with (
                pytest.raises(RestoreRejected, match="^INCREMENTAL_PG_FENCE_BUSY$"),
                pg_lock(owner, bound.binding.fence_key, exclusive=True),
            ):
                pytest.fail("shared service PG lock unexpectedly released")
        else:
            with pg_lock(owner, bound.binding.fence_key, exclusive=True):
                assert owner.execute("SELECT 1 AS ok").fetchone()["ok"] == 1


def pg_released(bound):
    deadline = time.monotonic() + 3
    while True:
        try:
            pg_exclusive(bound, busy=False)
            return
        except RestoreRejected as error:
            assert str(error) == "INCREMENTAL_PG_FENCE_BUSY"
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def assert_safe_output(stdout, stderr):
    assert PRIVATE_ERROR not in stdout + stderr and BODY not in stdout + stderr
    assert "password" not in stdout + stderr and "postgresql://" not in stdout + stderr


def test_actual_native_commits_background_and_both_fences_last_until_real_os_exit(bound, record_property):
    with service_child(bound) as child:
        child.state("native_ready")
        commits(bound)
        file_exclusive(bound, busy=True)
        pg_exclusive(bound, busy=True)
        child.send("return")
        child.state("native_finished")
        file_exclusive(bound, busy=True)
        pg_exclusive(bound, busy=True)
        child.send("exit")
        stdout, stderr = child.finish(0)
    assert_safe_output(stdout, stderr)
    assert stderr == "" and len(stdout.splitlines()) == 2
    file_exclusive(bound, busy=False)
    pg_released(bound)
    record_property("actual_native_commit_count", 2)
    record_property("native_finished_background_alive", True)
    record_property("sid_execute_preexisting", bound.actual["sid_execute_preexisting"])
    record_property("sid_test_grant_added", not bound.actual["sid_execute_preexisting"])
    record_property("full_application_or_linux_attestation", False)


def default_without_io(bound, monkeypatch, capsys):
    original_import = builtins.__import__

    def forbidden(*args, **kwargs):
        pytest.fail("default validation performed forbidden I/O or native dispatch")

    def imports(name, *args, **kwargs):
        if name.startswith(("mingjing_core", "uvicorn", "hermes")) or name == "main":
            pytest.fail("default validation imported native business")
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as changes:
        changes.setenv("ZHIMING_DATABASE_URL", bound.writer_dsn)
        assert not any(key.startswith("PG") and value for key, value in os.environ.items())
        for target, name in (
            (psycopg, "connect"),
            (subprocess, "Popen"),
            (launcher, "_native"),
            (os, "open"),
            (Path, "write_bytes"),
            (Path, "write_text"),
            (Path, "mkdir"),
        ):
            changes.setattr(target, name, forbidden)
        changes.setattr(builtins, "__import__", imports)
        assert launcher.main(bound.arguments) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "status": "validated",
        "role": "report",
        "database_connections": 0,
        "mutations": 0,
    }
    assert output.err == ""


def refused_child(bound, arguments=None):
    with service_child(bound, arguments=arguments) as child:
        stdout, stderr = child.finish(2)
    assert stdout == "" and stderr.strip() in {"SERVICE_CONFIGURATION_OR_FENCE_REJECTED", "SERVICE_START_REJECTED"}
    assert_safe_output(stdout, stderr)


def test_default_and_real_marker_lock_or_wrong_sid_reject_without_business(bound, monkeypatch, capsys):
    before = source_state(bound)
    original_fence = bound.binding.fence_path.read_bytes()
    default_without_io(bound, monkeypatch, capsys)
    assert source_state(bound) == before
    with file_lock(bound.binding.fence_path, exclusive=True, existing_only=True):
        refused_child(bound)
    with (
        psycopg.connect(bound.owner_dsn, autocommit=True, row_factory=dict_row) as owner,
        pg_lock(owner, bound.binding.fence_key, exclusive=True),
    ):
        refused_child(bound)
    wrong = list(bound.arguments)
    wrong[wrong.index("--system-identifier") + 1] = str(int(bound.binding.system_identifier) + 1)
    # The wrong identity still needs the explicit pre-existing lock path to reach actual PG identity verification.
    wrong_path = bound.binding.fence_path.with_name(
        str(int(bound.binding.system_identifier) + 1) + "-" + str(bound.binding.database_oid) + ".lock"
    )
    wrong_path.write_bytes(b"synthetic-wrong-sid-fence")
    refused_child(bound, [*wrong, "--run"])
    bound.binding.maintenance.write_bytes(b'{"synthetic_maintenance":true}')
    retained_marker = bound.binding.maintenance.read_bytes()
    refused_child(bound)
    assert source_state(bound) == before
    assert bound.binding.fence_path.read_bytes() == original_fence
    assert bound.binding.maintenance.read_bytes() == retained_marker


def test_native_exception_after_guard_backend_termination_keeps_os_fence_until_exit(bound, record_property):
    with service_child(bound, mode="raise") as child:
        child.state("native_ready")
        commits(bound)
        with psycopg.connect(bound.admin_dsn, autocommit=True, row_factory=dict_row) as admin:
            rows = admin.execute(
                "SELECT pid FROM pg_stat_activity WHERE datid=%s AND usesysid=%s "
                "AND application_name='first_release_service'",
                (bound.binding.database_oid, bound.binding.writer_oid),
            ).fetchall()
            assert len(rows) == 1
            assert admin.execute("SELECT pg_terminate_backend(%s,3000) AS ended", (rows[0]["pid"],)).fetchone()["ended"]
        file_exclusive(bound, busy=True)
        pg_exclusive(bound, busy=False)
        child.send("return")
        child.state("native_finished")
        file_exclusive(bound, busy=True)
        pg_exclusive(bound, busy=False)
        child.send("exit")
        stdout, stderr = child.finish(2)
    assert_safe_output(stdout, stderr)
    assert stderr == "SERVICE_NATIVE_FAILED\n" and len(stdout.splitlines()) == 2
    commits(bound)
    file_exclusive(bound, busy=False)
    pg_released(bound)
    record_property("dedicated_backend_terminated", True)
    record_property("actual_external_requests", 0)

"""Real source snapshots/dumps and cross-process cooperative fences; no global stop claim."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

import psycopg
import pytest
from first_release_support import ROOT, repin
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from test_first_release_candidate_preflight_pg import unpack
from test_first_release_local_restore_pg import pg_program, process_environment, seed

from tools import first_release_incremental_pg as pg
from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental import (
    CONTROL_NAMES,
    HERE,
    BackupInputs,
    SourcePin,
    execute,
    file_hash,
)


@dataclass
class Existing:
    inputs: BackupInputs
    environment: dict = field(repr=False)
    admin: str = field(repr=False)


@pytest.fixture(scope="module")
def archive():
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    head = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    content = subprocess.run(
        ["git", "archive", "--format=tar", head],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=True,
    ).stdout
    return head, content


def create_source(admin_dsn, database, credentials):
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        for role in ("owner", "writer"):
            name = database + "_" + role
            verifier = admin.pgconn.encrypt_password(
                credentials[role].encode(), name.encode(), b"scram-sha-256"
            ).decode()
            admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(name), sql.Literal(verifier))
            )
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'").format(
                sql.Identifier(database), sql.Identifier(database + "_owner")
            )
        )
        admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
        admin.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), sql.Identifier(database + "_writer")
            )
        )
    with psycopg.connect(make_conninfo(admin_dsn, dbname=database)) as admin:
        admin.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(database + "_owner")))


def metadata(admin_dsn, database):
    with psycopg.connect(admin_dsn, row_factory=dict_row) as admin:
        identity = admin.execute("SELECT (pg_control_system()).system_identifier::text AS system_identifier").fetchone()
        info = admin.execute(
            "SELECT oid AS database_oid,datdba AS owner_oid FROM pg_database WHERE datname=%s",
            (database,),
        ).fetchone()
        writer = admin.execute(
            "SELECT oid AS writer_oid FROM pg_roles WHERE rolname=%s",
            (database + "_writer",),
        ).fetchone()
    return dict(identity, **info, **writer)


def backup_inputs(ident, release, source, workspace):
    configured = os.environ.get("FIRST_RELEASE_CANDIDATE_TEST_PYTHON")
    fallback = ROOT.parent / "zhiming-v4/.venv-k3/Scripts/python.exe" if os.name == "nt" else Path(sys.executable)
    python = Path(configured) if configured else fallback
    return BackupInputs(
        "fr-" + ident,
        release,
        source,
        python,
        pg_program("pg_dump"),
        file_hash(python),
        file_hash(pg_program("pg_dump")),
        tuple(sorted((name, file_hash(HERE / name)) for name in CONTROL_NAMES)),
        workspace,
    )


@pytest.fixture
def existing(request, archive):
    prefix, ident = getattr(request, "param", 7), uuid.uuid4().hex
    admin = os.environ.get("FIRST_RELEASE_LOCAL_TEST_ADMIN_DSN") or os.environ.get("CORE_TEST_DSN", "")
    fields = conninfo_to_dict(admin)
    assert fields.get("host") in {"127.0.0.1", "::1"} and fields.get("port") in {
        "55480",
        "55481",
    }
    database = "fr_upgrade_" + ident
    credentials = {role: secrets.token_urlsafe(24) for role in ("owner", "writer")}
    with tempfile.TemporaryDirectory(prefix="frib-") as directory:
        workspace = Path(directory)
        root = workspace / "private" / ("first-incremental-" + ident) / archive[0]
        unpack(root, archive[1])
        release = repin(root)
        create_source(admin, database, credentials)
        env = {"FIRST_INCREMENTAL_ADMIN_DSN": admin}
        for role in ("owner", "writer"):
            env["FIRST_INCREMENTAL_" + role.upper() + "_DSN"] = make_conninfo(
                host=fields["host"],
                port=fields["port"],
                dbname=database,
                user=database + "_" + role,
                password=credentials[role],
            )
        try:
            seed(env["FIRST_INCREMENTAL_OWNER_DSN"], prefix, dict(release.migrations))
            with psycopg.connect(env["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
                owner.execute(
                    "INSERT INTO mingjing_core.core_revocations(owner,kind,entity_id,operation,revision) "
                    "VALUES('synthetic','legacy_memory','synthetic-old','synthetic-revocation',1)"
                )
                owner.execute("CREATE SEQUENCE mingjing_core.synthetic_backup_seq START 11")
                owner.execute("SELECT nextval('mingjing_core.synthetic_backup_seq')")
            pinned = SourcePin(
                database=database,
                **metadata(admin, database),
                owners=("synthetic",),
                migrations=tuple((str(v), dict(release.migrations)[str(v)]) for v in range(1, prefix + 1)),
            )
            inputs = backup_inputs(ident, release, pinned, workspace)
            yield Existing(inputs, env, admin)
        finally:
            with psycopg.connect(admin, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
                for role in ("owner", "writer"):
                    connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(database + "_" + role)))


def state(existing):
    with psycopg.connect(existing.environment["FIRST_INCREMENTAL_OWNER_DSN"], row_factory=dict_row) as owner:
        return pg.snapshot(owner)


@contextmanager
def inspect_dump(existing):
    name = "fr_inspect_" + uuid.uuid4().hex
    with psycopg.connect(existing.admin, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
    try:
        fields = conninfo_to_dict(existing.admin)
        command = [
            str(pg_program("pg_restore")),
            "--host=" + fields["host"],
            "--port=" + fields["port"],
            "--username=" + fields["user"],
            "--dbname=" + name,
            "--no-password",
            "--no-owner",
            "--no-acl",
            "--exit-on-error",
            "--single-transaction",
            str(existing.inputs.operation_dir / "backup.dump"),
        ]
        restored = subprocess.run(
            command,
            env=process_environment(existing.admin),
            capture_output=True,
            timeout=90,
        )
        assert restored.returncode == 0, "ACTUAL_PRIVATE_INSPECT_RESTORE_FAILED"
        with psycopg.connect(make_conninfo(existing.admin, dbname=name), row_factory=dict_row) as connection:
            yield connection
    finally:
        with psycopg.connect(existing.admin, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.mark.parametrize("existing", [4, 7], indirect=True)
def test_actual_existing_source_capture_and_restored_snapshot_match_without_source_upgrade(
    existing,
):
    before = state(existing)
    result = execute(existing.inputs, backup_local=True, environment=existing.environment)
    assert result["backup_captured"] is result["same_mvcc_snapshot"] is result["maintenance_retained"] is True
    assert (
        result["global_quiescence_verified"]
        is result["source_upgraded"]
        is result["source_restore_content_verified"]
        is False
    )
    assert result["session_checks"] == "before_after" and state(existing) == before
    document = json.loads((existing.inputs.operation_dir / "latest-withdrawals.json").read_text())
    assert document["owners"][0]["revocations"][0]["entity_id"] == "synthetic-old"
    evidence = json.loads((existing.inputs.operation_dir / "backup-receipt.json").read_text())["source_snapshots"]
    assert evidence["before"] == evidence["after"] == before
    assert set(before["sequences"]["mingjing_core.synthetic_backup_seq"]) == {
        "last_value",
        "log_cnt",
        "is_called",
    }
    with inspect_dump(existing) as restored:
        restored_state = pg.snapshot(restored)
        assert restored_state["tables"] == before["tables"], "RESTORED_ORIGINAL_TABLE_FIELDS_DIFFER"
        sequence = restored_state["sequences"]["mingjing_core.synthetic_backup_seq"]
        assert sequence["last_value"] == 11 and sequence["is_called"] is True
    for key in (
        "native_restore_completed",
        "runtime_verified",
        "central_binding_verified",
        "linux_attestation",
        "publication",
    ):
        assert result[key] is False


def test_default_has_no_connections_processes_or_files_and_exact_oid_mismatch_never_backs_up(existing, monkeypatch):
    real_connect, real_run = psycopg.connect, subprocess.run

    def forbidden(*args, **kwargs):
        pytest.fail("DEFAULT_VALIDATION_MUST_NOT_CONNECT_OR_SPAWN")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    result = execute(existing.inputs)
    assert result["database_connections"] == result["processes"] == result["file_writes"] == 0
    assert not existing.inputs.fence_path.parent.exists()
    monkeypatch.setattr(psycopg, "connect", real_connect)
    monkeypatch.setattr(subprocess, "run", real_run)
    wrong = replace(
        existing.inputs,
        source=replace(existing.inputs.source, database_oid=existing.inputs.source.database_oid + 1),
    )
    with pytest.raises(RestoreRejected, match="INCREMENTAL_SOURCE_DATABASE_OID"):
        execute(wrong, backup_local=True, environment=existing.environment)
    assert not (existing.inputs.operation_dir / "backup.dump").exists()


def test_extra_real_session_is_not_allowed_by_spoofed_application_name(existing):
    before = state(existing)
    with (
        psycopg.connect(
            make_conninfo(
                existing.environment["FIRST_INCREMENTAL_OWNER_DSN"],
                application_name="pg_dump",
            )
        ),
        pytest.raises(RestoreRejected, match="INCREMENTAL_OTHER_SOURCE_SESSION"),
    ):
        execute(existing.inputs, backup_local=True, environment=existing.environment)
    assert state(existing) == before and not existing.inputs.maintenance.exists()


def test_active_lease_is_refused_without_changing_or_revoking_source_run(existing):
    with psycopg.connect(existing.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
        owner.execute(
            "INSERT INTO mingjing_core.core_runs(id,owner,subject,operation_id,fingerprint,request,"
            "call_limit,status,lease_until) VALUES('synthetic-run','synthetic','self','synthetic-run','synthetic',"
            "'{}',2,'failed',now()+interval '1 hour')"
        )
    before = state(existing)
    with pytest.raises(RestoreRejected, match="INCREMENTAL_ACTIVE_RUN_OR_LEASE"):
        execute(existing.inputs, backup_local=True, environment=existing.environment)
    assert state(existing) == before and not existing.inputs.maintenance.exists()


HOLDER = """import json,sys,psycopg
from pathlib import Path
from psycopg.rows import dict_row
from tools.first_release_writer_fence import file_lock,pg_lock
value=json.loads(sys.stdin.readline())
if value['kind']=='file':
    with file_lock(Path(value['path']),exclusive=False):
        print('ready',flush=True);sys.stdin.readline()
else:
    with psycopg.connect(value['dsn'],autocommit=True,row_factory=dict_row) as c:
        with pg_lock(c,value['key'],exclusive=False):
            print('ready',flush=True);sys.stdin.readline()
"""


@pytest.mark.parametrize("kind", ["file", "pg"])
def test_real_cross_process_shared_writer_blocks_exclusive_backup(existing, kind):
    existing.inputs.fence_path.parent.mkdir(parents=True)
    env = pg.environment("")
    child = subprocess.Popen(
        [sys.executable, "-c", HOLDER],
        cwd=ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        child.stdin.write(
            json.dumps(
                {
                    "kind": kind,
                    "path": str(existing.inputs.fence_path),
                    "dsn": existing.environment["FIRST_INCREMENTAL_OWNER_DSN"],
                    "key": existing.inputs.fence_key,
                }
            )
            + "\n"
        )
        child.stdin.flush()
        assert child.stdout.readline().strip() == "ready", "REAL_WRITER_FENCE_HOLDER_NOT_READY"
        with pytest.raises(RestoreRejected, match="INCREMENTAL_" + kind.upper() + "_FENCE_BUSY"):
            execute(existing.inputs, backup_local=True, environment=existing.environment)
        assert not existing.inputs.maintenance.exists()
        child.communicate("release\n", timeout=10)
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate()


def test_dump_and_native_ledger_share_snapshot_but_fresh_source_drift_stops_and_retains_outputs(existing, monkeypatch):
    original = pg.candidate_export

    def after_snapshot(inputs, dsn, connection, snapshot_id):
        with psycopg.connect(dsn) as intruder:
            intruder.execute(
                "INSERT INTO mingjing_core.core_revocations(owner,kind,entity_id,operation,revision) "
                "VALUES('synthetic','legacy_memory','synthetic-late','synthetic-late',2)"
            )
            intruder.execute("SELECT nextval('mingjing_core.synthetic_backup_seq')")
        return original(inputs, dsn, connection, snapshot_id)

    monkeypatch.setattr(pg, "candidate_export", after_snapshot)
    with pytest.raises(RestoreRejected, match="INCREMENTAL_SOURCE_CHANGED_OUTPUTS_RETAINED"):
        execute(existing.inputs, backup_local=True, environment=existing.environment)
    assert existing.inputs.maintenance.exists() and (existing.inputs.operation_dir / "backup.dump").is_file()
    document = json.loads((existing.inputs.operation_dir / "latest-withdrawals.json").read_text())
    assert "synthetic-late" not in json.dumps(document), "NATIVE_EXPORT_DID_NOT_IMPORT_EXPORTED_SNAPSHOT"
    with inspect_dump(existing) as restored:
        assert (
            restored.execute("SELECT 1 FROM mingjing_core.core_revocations WHERE entity_id='synthetic-late'").fetchone()
            is None
        )
    with psycopg.connect(existing.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as source:
        assert source.execute(
            "SELECT 1 FROM mingjing_core.core_revocations WHERE entity_id='synthetic-late'"
        ).fetchone()
    assert not (existing.inputs.operation_dir / "backup-receipt.json").exists()


COOPERATIVE = """import json,sys,psycopg
from pathlib import Path
from psycopg.rows import dict_row
from tools.first_release_writer_fence import cooperative_writer
from tools.first_release_contracts import RestoreRejected
value=json.loads(sys.stdin.readline())
for entity in ('synthetic-writer-before','synthetic-writer-after'):
    if sys.stdin.readline().strip()!='write':raise SystemExit(2)
    try:
        with psycopg.connect(value['dsn'],autocommit=True,row_factory=dict_row) as c:
            with cooperative_writer(c,Path(value['path']),value['key'],Path(value['marker'])):
                c.execute("INSERT INTO mingjing_core.core_revocations(owner,kind,entity_id,operation,revision) "
                          "VALUES('synthetic','legacy_memory',%s,%s,3)",(entity,entity))
        result='written'
    except RestoreRejected as error:
        result=str(error)
    print(result,flush=True)
"""


def test_persistent_marker_blocks_real_cooperative_writer_after_backup_locks_are_released(existing):
    existing.inputs.fence_path.parent.mkdir(parents=True)
    child = subprocess.Popen(
        [sys.executable, "-c", COOPERATIVE],
        cwd=ROOT,
        env=pg.environment(""),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        value = {
            "dsn": existing.environment["FIRST_INCREMENTAL_OWNER_DSN"],
            "path": str(existing.inputs.fence_path),
            "key": existing.inputs.fence_key,
            "marker": str(existing.inputs.maintenance),
        }
        child.stdin.write(json.dumps(value) + "\nwrite\n")
        child.stdin.flush()
        assert child.stdout.readline().strip() == "written", "COOPERATIVE_WRITER_POSITIVE_WRITE_NOT_REACHED"
        before = state(existing)
        result = execute(existing.inputs, backup_local=True, environment=existing.environment)
        assert result["backup_captured"] and existing.inputs.maintenance.is_file()
        child.stdin.write("write\n")
        child.stdin.flush()
        assert child.stdout.readline().strip() == "INCREMENTAL_MAINTENANCE_RETAINED"
        child.communicate(timeout=10)
        assert child.returncode == 0 and state(existing) == before
        with psycopg.connect(existing.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as source:
            found = source.execute(
                "SELECT entity_id FROM mingjing_core.core_revocations WHERE entity_id=ANY(%s)",
                (["synthetic-writer-before", "synthetic-writer-after"],),
            ).fetchall()
        assert found == [("synthetic-writer-before",)], "MAINTENANCE_MARKER_FAILED_TO_BLOCK_REAL_WRITE"
        assert existing.inputs.maintenance.is_file()
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate()

"""Real PG15 archive ownership/ACL preservation and closed, zero-client database exchange."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from test_first_release_local_restore_pg import pg_program

from tools.first_release_contracts import RestoreRejected
from tools.first_release_database_metadata import capture, semantic
from tools.first_release_local_restore import process_environment
from tools.first_release_native_exchange import Scope, control, exchange, file_hash, main, restore_new, seal


@dataclass
class Sample:
    scope: Scope
    environment: dict[str, str]
    admin: str
    backup: Path
    owner: str
    reader: str
    metadata: dict


def db_dsn(sample: Sample, name: str) -> str:
    return make_conninfo(sample.admin, dbname=name)


def set_closed(sample: Sample, name: str) -> None:
    with psycopg.connect(sample.admin, autocommit=True) as admin:
        admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(name)))


def dump(sample: Sample) -> None:
    fields = conninfo_to_dict(sample.admin)
    result = subprocess.run(
        [
            str(pg_program("pg_dump")),
            "--host=" + fields["host"],
            "--port=" + fields["port"],
            "--username=" + fields["user"],
            "--dbname=" + sample.scope.original,
            "--format=custom",
            "--no-password",
            "--file=" + str(sample.backup),
        ],
        env=process_environment(sample.admin),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, "private dump diagnostic withheld"


def initialize(sample: Sample) -> None:
    with psycopg.connect(sample.admin, autocommit=True) as admin:
        for name in (sample.owner, sample.reader):
            admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(name)))
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(sample.scope.original),
                sql.Identifier(sample.owner),
            )
        )
        admin.execute(
            sql.SQL("REVOKE CONNECT,TEMPORARY ON DATABASE {} FROM PUBLIC").format(sql.Identifier(sample.scope.original))
        )
        admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(sample.owner)))
        admin.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {} WITH GRANT OPTION").format(
                sql.Identifier(sample.scope.original),
                sql.Identifier(sample.reader),
            )
        )
        admin.execute("RESET ROLE")
        admin.execute(
            sql.SQL("ALTER DATABASE {} SET search_path TO synthetic,pg_catalog").format(
                sql.Identifier(sample.scope.original)
            )
        )
        admin.execute(
            sql.SQL("ALTER ROLE {} IN DATABASE {} SET timezone TO 'Asia/Tokyo'").format(
                sql.Identifier(sample.reader),
                sql.Identifier(sample.scope.original),
            )
        )
    with psycopg.connect(db_dsn(sample, sample.scope.original)) as source:
        source.execute("CREATE SCHEMA synthetic")
        source.execute("CREATE TABLE synthetic.core_runs(run_id text PRIMARY KEY, body text)")
        source.execute("INSERT INTO synthetic.core_runs VALUES('before','SYNTHETIC_PRIVATE_ORIGINAL')")
        source.execute(sql.SQL("ALTER TABLE synthetic.core_runs OWNER TO {}").format(sql.Identifier(sample.owner)))
        source.execute(sql.SQL("GRANT USAGE ON SCHEMA synthetic TO {}").format(sql.Identifier(sample.reader)))
        source.execute(sql.SQL("GRANT SELECT ON synthetic.core_runs TO {}").format(sql.Identifier(sample.reader)))


@pytest.fixture
def sample(tmp_path):
    configured = os.environ.get("FIRST_RELEASE_LOCAL_TEST_ADMIN_DSN") or os.environ.get("CORE_TEST_DSN", "")
    fields = conninfo_to_dict(configured)
    assert fields.get("host") in {"127.0.0.1", "::1"} and fields.get("port") in {"55480", "55481"}
    assert fields.get("dbname") in {"postgres", "core_test_main"}
    admin = make_conninfo(
        **{
            key: value
            for key, value in fields.items()
            if key
            in {
                "host",
                "port",
                "dbname",
                "user",
                "password",
                "connect_timeout",
            }
        }
    )
    scope = Scope(uuid.uuid4().hex[:16], local_drill=True)
    value = Sample(
        scope,
        {"FIRST_RELEASE_EXCHANGE_ADMIN_DSN": admin},
        admin,
        tmp_path / "original.dump",
        "frx_" + scope.operation + "_owner",
        "frx_" + scope.operation + "_reader",
        {},
    )
    try:
        initialize(value)
        dump(value)
        with control(scope, value.environment) as (connection, _):
            value.metadata = capture(connection, scope.original)
        yield value
    finally:
        # Fixture-only cleanup of these exact new synthetic names; the tool never deletes anything.
        with psycopg.connect(admin, autocommit=True) as connection:
            for name in (scope.original, scope.replacement, scope.failed):
                assert name.startswith("frx_" + scope.operation + "_")
                connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
            for name in (value.reader, value.owner):
                connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(name)))


def test_explicit_restore_endpoint_wins_over_distinct_core_ci_endpoint(monkeypatch, tmp_path):
    configured = os.environ.get("FIRST_RELEASE_LOCAL_TEST_ADMIN_DSN") or os.environ["CORE_TEST_DSN"]
    monkeypatch.setenv("FIRST_RELEASE_LOCAL_TEST_ADMIN_DSN", configured)
    monkeypatch.setenv("CORE_TEST_DSN", "postgresql://ignored_core@127.0.0.1:5432/core_test")
    generator = sample.__wrapped__(tmp_path)
    try:
        value = next(generator)
        with control(value.scope, value.environment) as (connection, _):
            assert connection.execute("SELECT inet_server_port() AS port").fetchone()["port"] in {55480, 55481}
    finally:
        generator.close()


def restore(sample: Sample) -> dict:
    program = pg_program("pg_restore")
    return restore_new(
        sample.scope,
        sample.metadata,
        sample.backup,
        file_hash(sample.backup),
        program,
        file_hash(program),
        environment=sample.environment,
    )


def test_actual_foreign_key_clean_failure_then_new_restore_preserves_owner_acl_settings_and_old_database(sample):
    with psycopg.connect(db_dsn(sample, sample.scope.original)) as source:
        source.execute("ALTER TABLE synthetic.core_runs ADD COLUMN parent_run_id text")
        source.execute(
            "ALTER TABLE synthetic.core_runs ADD CONSTRAINT core_runs_parent_run_id_fkey "
            "FOREIGN KEY(parent_run_id) REFERENCES synthetic.core_runs(run_id)"
        )
        source.execute("INSERT INTO synthetic.core_runs(run_id,body) VALUES('after','SYNTHETIC_FAILED_VERSION')")
    fields = conninfo_to_dict(sample.admin)
    bad = subprocess.run(
        [
            str(pg_program("pg_restore")),
            "--host=" + fields["host"],
            "--port=" + fields["port"],
            "--username=" + fields["user"],
            "--dbname=" + sample.scope.original,
            "--clean",
            "--if-exists",
            "--single-transaction",
            "--no-password",
            str(sample.backup),
        ],
        env=process_environment(sample.admin),
        capture_output=True,
        timeout=30,
    )
    assert bad.returncode != 0 and b"core_runs_pkey" in bad.stderr
    receipt = restore(sample)
    set_closed(sample, sample.scope.original)
    result = exchange(sample.scope, sample.metadata, receipt, environment=sample.environment)
    with control(sample.scope, sample.environment) as (connection, _):
        current, failed = capture(connection, sample.scope.original), capture(connection, sample.scope.failed)
        assert current["oid"] == receipt["replacement_oid"] and failed["oid"] == sample.metadata["oid"]
        assert semantic(current) == semantic(sample.metadata) == semantic(failed)
        assert (
            connection.execute(
                "SELECT datallowconn FROM pg_catalog.pg_database WHERE oid=ANY(%s)", ([current["oid"], failed["oid"]],)
            ).fetchall()
            == [{"datallowconn": False}] * 2
        )
        # Test-only read reopening follows the assertions; the exchange itself leaves both closed.
        connection.execute(
            sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(sample.scope.original))
        )
        connection.execute(
            sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(sample.scope.failed))
        )
    for name, expected in ((sample.scope.original, ["before"]), (sample.scope.failed, ["after", "before"])):
        with psycopg.connect(db_dsn(sample, name), row_factory=dict_row) as connection:
            assert [
                row["run_id"] for row in connection.execute("SELECT run_id FROM synthetic.core_runs ORDER BY run_id")
            ] == expected
            row = connection.execute(
                "SELECT tableowner FROM pg_catalog.pg_tables WHERE schemaname='synthetic' AND tablename='core_runs'"
            ).fetchone()
            assert row["tableowner"] == sample.owner
            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(sample.reader)))
            assert connection.execute("SELECT count(*) AS n FROM synthetic.core_runs").fetchone()["n"] == len(expected)
    assert result["admission_opened"] is result["old_database_deleted"] is result["production"] is False


def isolated_cli(sample, arguments, output):
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    environment["FIRST_RELEASE_EXCHANGE_ADMIN_DSN"] = sample.admin
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys;sys.path.insert(0,sys.argv.pop(1));"
            "from tools.first_release_native_exchange import main;raise SystemExit(main())",
            str(Path(__file__).resolve().parents[3]),
            *arguments,
        ],
        env=environment,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, "native isolated CLI failed; private diagnostic withheld"
    output.append(result.stdout.decode())
    return result.returncode


def test_public_cli_capture_restore_exchange_writes_private_receipts_without_echoing_secrets(sample, tmp_path):
    output = []

    def cli(arguments):
        return isolated_cli(sample, arguments, output)

    metadata, receipt = tmp_path / "db-metadata.json", tmp_path / "restore-receipt.json"
    common = ["--operation", sample.scope.operation, "--local-drill", "--metadata", str(metadata)]
    assert cli(["capture", *common, "--output", str(tmp_path / "capture-receipt.json")]) == 0
    program = pg_program("pg_restore")
    pinned = [*common, "--metadata-sha256", file_hash(metadata)]
    assert (
        cli(
            [
                "restore",
                *pinned,
                "--backup",
                str(sample.backup),
                "--backup-sha256",
                file_hash(sample.backup),
                "--pg-restore",
                str(program),
                "--pg-restore-sha256",
                file_hash(program),
                "--output",
                str(receipt),
            ]
        )
        == 0
    )
    assert cli(["seal", *pinned, "--output", str(tmp_path / "seal-receipt.json")]) == 0
    assert (
        cli(
            [
                "exchange",
                *pinned,
                "--restore-receipt",
                str(receipt),
                "--restore-receipt-sha256",
                file_hash(receipt),
                "--output",
                str(tmp_path / "exchange-receipt.json"),
            ]
        )
        == 0
    )
    with control(sample.scope, sample.environment) as (connection, _):
        assert capture(connection, sample.scope.original)["oid"] != sample.metadata["oid"]
        assert capture(connection, sample.scope.failed)["oid"] == sample.metadata["oid"]
    public = "".join(output)
    assert "SYNTHETIC_PRIVATE" not in public and sample.admin not in public and "postgresql://" not in public


def test_existing_client_prevents_exchange_without_renaming_or_terminating_it(sample):
    receipt = restore(sample)
    with psycopg.connect(db_dsn(sample, sample.scope.original)) as active:
        with pytest.raises(RestoreRejected, match="EXCHANGE_CLIENTS_REMAIN_DATABASE_KEPT_CLOSED"):
            seal(sample.scope, sample.metadata, environment=sample.environment)
        with pytest.raises(RestoreRejected, match="EXCHANGE_REQUIRES_CLOSED_ZERO_CONNECTIONS"):
            exchange(sample.scope, sample.metadata, receipt, environment=sample.environment)
        assert active.execute("SELECT count(*) FROM synthetic.core_runs").fetchone() == (1,)
        with control(sample.scope, sample.environment) as (connection, _):
            assert capture(connection, sample.scope.original)["oid"] == sample.metadata["oid"]
            assert capture(connection, sample.scope.replacement)["oid"] == receipt["replacement_oid"]
            assert (
                connection.execute(
                    "SELECT oid FROM pg_catalog.pg_database WHERE datname=%s", (sample.scope.failed,)
                ).fetchone()
                is None
            )


def test_changed_backup_fails_before_database_creation_and_existing_restore_is_never_adopted(sample):
    program = pg_program("pg_restore")
    with pytest.raises(RestoreRejected, match="EXCHANGE_BACKUP_CHANGED"):
        restore_new(
            sample.scope,
            sample.metadata,
            sample.backup,
            "0" * 64,
            program,
            file_hash(program),
            environment=sample.environment,
        )
    with control(sample.scope, sample.environment) as (connection, _):
        assert (
            connection.execute(
                "SELECT oid FROM pg_catalog.pg_database WHERE datname=%s", (sample.scope.replacement,)
            ).fetchone()
            is None
        )
    receipt = restore(sample)
    with pytest.raises(RestoreRejected, match="EXCHANGE_NEW_NAME_ALREADY_EXISTS"):
        restore(sample)
    with control(sample.scope, sample.environment) as (connection, _):
        assert capture(connection, sample.scope.replacement)["oid"] == receipt["replacement_oid"]


def test_formal_cli_requires_protected_admin_file_before_opening_a_database(tmp_path, capsys):
    metadata, receipt = tmp_path / "metadata.json", tmp_path / "receipt.json"
    assert main(["capture", "--operation", "a" * 16, "--metadata", str(metadata), "--output", str(receipt)]) == 2
    assert "EXCHANGE_PROTECTED_ADMIN_FILE_REQUIRED" in capsys.readouterr().out
    assert not metadata.exists() and not receipt.exists()

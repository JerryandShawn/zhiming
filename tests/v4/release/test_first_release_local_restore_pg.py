"""Actual PG15 dump/restore into fresh local identities; never formal readiness evidence."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import psycopg
import pytest
from first_release_support import ROOT, contract_document, packed_source, pin_document, write_json
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.runtime import LangGraphRuntime
from tools.first_release_contracts import RestoreRejected
from tools.first_release_local_inputs import DumpPin, LocalInputs, file_hash
from tools.first_release_local_restore import execute, main, process_environment

PG_BIN = Path("C:/Users/Administrator/Documents/Codex/2026-10-11/p-jerrymeng-asia-1-14-59/work/postgres/pgsql/bin")
PRIVATE = "SYNTHETIC_PRIVATE_RESTORE_BODY"


def pg_program(name: str) -> Path:
    configured = os.environ.get("FIRST_RELEASE_TEST_PG_BIN")
    if configured:
        path = Path(configured) / (name + ".exe" if os.name == "nt" else name)
    elif os.name == "nt":
        path = PG_BIN / (name + ".exe")
    else:
        found = shutil.which(name)
        assert found, "actual PostgreSQL15 clients must be installed; no silent skip"
        path = Path(found)
    assert path.is_absolute() and path.is_file() and not path.is_symlink(), "explicit ordinary PG15 client required"
    version = subprocess.run([str(path), "--version"], env=process_environment(""), capture_output=True, timeout=10)
    assert version.returncode == 0 and re.search(rb"PostgreSQL\) 15\.[0-9]+", version.stdout), "PG15 client required"
    return path


@dataclass
class Sample:
    inputs: LocalInputs
    admin: str = field(repr=False)
    source: str = field(repr=False)
    environment: dict[str, str] = field(repr=False)

    def dump(self) -> None:
        fields = conninfo_to_dict(self.source)
        program = pg_program("pg_dump")
        command = [
            str(program),
            "--host=" + fields["host"],
            "--port=" + fields["port"],
            "--username=" + fields["user"],
            "--dbname=" + fields["dbname"],
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--no-password",
            "--file=" + str(self.inputs.dump),
        ]
        result = subprocess.run(command, env=process_environment(self.source), capture_output=True, timeout=60)
        assert result.returncode == 0, "actual local synthetic pg_dump failed; private diagnostic withheld"
        self.inputs = replace(
            self.inputs, dump_pin=replace(self.inputs.dump_pin, dump_sha256=file_hash(self.inputs.dump))
        )

    def present(self) -> tuple[bool, int]:
        name = self.inputs.contract.database
        with psycopg.connect(self.admin) as admin:
            return admin.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=%s),"
                "(SELECT count(*) FROM pg_roles WHERE rolname=ANY(%s))",
                (name, [name + "_owner", name + "_writer"]),
            ).fetchone()


def seed(source: str, prefix: int, migrations: dict[str, str]) -> None:
    with psycopg.connect(source) as connection:
        connection.execute("CREATE SCHEMA mingjing_core")
        connection.execute("SET LOCAL search_path=mingjing_core")
        connection.execute(
            "CREATE TABLE schema_migrations(version integer PRIMARY KEY,checksum text,"
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for version in range(1, prefix + 1):
            path = next((ROOT / "mingjing_core/repositories/migrations").glob(f"{version:04d}_*.sql"))
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)", (version, migrations[str(version)])
            )
        connection.execute("INSERT INTO core_owners(id) VALUES('synthetic')")
        connection.execute("INSERT INTO core_subjects(owner,id,label) VALUES('synthetic','self','synthetic')")
        connection.execute(
            "INSERT INTO core_entities(owner,kind,id,subject,data) "
            "VALUES('synthetic','message','synthetic-message','self',%s)",
            (Jsonb({"text": PRIVATE}),),
        )
        if prefix == 8:
            connection.execute(
                "INSERT INTO core_model_accounts(account_id,ledger_identity,location_id) VALUES(%s,%s,%s)",
                ("synthetic-account", uuid.uuid4(), "a" * 64),
            )
    repo = PostgresRepository(source, initialize=False)
    try:
        LangGraphRuntime(repo)
    finally:
        repo.close()


@pytest.fixture
def sample(request, tmp_path_factory):
    prefix = getattr(request, "param", 4)
    configured = os.environ.get("FIRST_RELEASE_LOCAL_TEST_ADMIN_DSN") or os.environ.get("CORE_TEST_DSN", "")
    fields = conninfo_to_dict(configured)
    assert fields.get("host") in {"127.0.0.1", "::1"} and fields.get("port") in {"55480", "55481"}, (
        "explicit disposable FIRST_RELEASE_LOCAL_TEST_ADMIN_DSN on actual55480/55481 required; no production fallback"
    )
    assert fields.get("dbname") in {"core_test_main", "postgres"}, (
        "dedicated disposable local admin control DB required"
    )
    workspace = tmp_path_factory.mktemp("frl")
    release, contract = packed_source(workspace)
    program = pg_program("pg_restore")
    source_name = "fr_source_" + uuid.uuid4().hex
    with psycopg.connect(configured, autocommit=True) as admin:
        assert 150000 <= admin.info.server_version < 160000
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(source_name)))
    source = make_conninfo(configured, dbname=source_name)
    roles = [contract.database + "_owner", contract.database + "_writer"]
    environment = {"FIRST_RELEASE_ADMIN_DSN": configured}
    for role in ("owner", "writer"):
        environment["FIRST_RELEASE_" + role.upper() + "_DSN"] = make_conninfo(
            host=fields["host"],
            port=fields["port"],
            dbname=contract.database,
            user=contract.database + "_" + role,
            password=secrets.token_urlsafe(32),
        )
    inputs = LocalInputs(
        release,
        contract,
        DumpPin(
            release.candidate,
            release.manifest_sha256,
            "0" * 64,
            file_hash(program),
            tuple((str(v), dict(release.migrations)[str(v)]) for v in range(1, min(prefix, 7) + 1)),
        ),
        contract.candidate_source.parent / "backup.dump",
        program,
        workspace,
    )
    value = Sample(inputs, configured, source, environment)
    try:
        seed(source, prefix, dict(release.migrations))
        value.dump()
        yield value
    finally:
        # Test-only cleanup is outside the tool; only this fixture's exact new random names are eligible.
        assert source_name.startswith("fr_source_") and contract.database.startswith("fr_restore_")
        with psycopg.connect(configured, autocommit=True) as admin:
            for name in (source_name, contract.database):
                if admin.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                    admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            for role in roles:
                if admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.mark.parametrize("sample", [4, 7], indirect=True)
def test_actual_restore_preserves_original_prefix_data_and_new_owner_without_forward_migration(sample):
    result = execute(sample.inputs, apply_local=True, environment=sample.environment)
    assert result["actual_pg_restore"] is result["local_pg_restore_completed"] is True
    assert result["database_connections"] == 4
    assert result["original_prefix"] == dict(sample.inputs.dump_pin.source_migrations)
    assert result["forward_migrations"] == [] and result["central_ledger_present"] is False
    assert result["latest_withdrawals_replayed"] is result["runtime_acl_verified"] is False
    assert result["native_restore_completed"] is result["linux_attestation"] is result["publication"] is False
    assert PRIVATE not in json.dumps(result) and sample.present() == (True, 2)
    with psycopg.connect(sample.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
        assert owner.execute(
            "SELECT data FROM mingjing_core.core_entities WHERE id='synthetic-message'"
        ).fetchone() == ({"text": PRIVATE},)
        assert owner.execute("SELECT count(*) FROM public.checkpoint_migrations").fetchone()[0] > 0
        assert owner.execute(
            "SELECT pg_get_userbyid(nspowner)=current_user FROM pg_namespace WHERE nspname='public'"
        ).fetchone() == (True,)
        assert owner.execute("SELECT NOT rolinherit FROM pg_roles WHERE rolname=current_user").fetchone() == (True,)
        assert owner.execute(
            "SELECT has_schema_privilege(%s,'public','CREATE')", (sample.inputs.contract.database + "_writer",)
        ).fetchone() == (False,)
    with pytest.raises(RestoreRejected, match="ALREADY_EXISTS"):
        execute(sample.inputs, apply_local=True, environment=sample.environment)


def test_default_validation_does_not_connect_create_or_execute_pg_restore(sample, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("default validation must not connect or spawn a process")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    result = execute(sample.inputs, environment=sample.environment)
    assert result["database_connections"] == result["mutations"] == 0
    assert result["local_pg_restore_completed"] is False


@pytest.mark.parametrize("apply", [False, True])
def test_formal_scope_is_hard_rejected_even_before_looking_for_inputs(sample, apply):
    inputs = replace(sample.inputs, contract=replace(sample.inputs.contract, local_drill=False))
    with pytest.raises(RestoreRejected, match="LOCAL_DRILL_ONLY"):
        execute(inputs, apply_local=apply, environment=sample.environment)
    assert sample.present() == (False, 0)


@pytest.mark.parametrize("kind", ["database", "owner", "writer"])
def test_existing_database_or_either_role_is_never_adopted_or_changed(sample, kind):
    name = sample.inputs.contract.database
    with psycopg.connect(sample.admin, autocommit=True) as admin:
        query = sql.SQL("CREATE DATABASE {}") if kind == "database" else sql.SQL("CREATE ROLE {} NOLOGIN")
        admin.execute(query.format(sql.Identifier(name if kind == "database" else name + "_" + kind)))
    before = sample.present()
    with pytest.raises(RestoreRejected, match="ALREADY_EXISTS"):
        execute(sample.inputs, apply_local=True, environment=sample.environment)
    assert sample.present() == before


@pytest.mark.parametrize("kind", ["dump", "binary", "prefix8", "candidate"])
def test_reviewed_input_changes_are_rejected_before_creating_any_objects(sample, kind):
    inputs = sample.inputs
    if kind == "dump":
        inputs.dump.write_bytes(inputs.dump.read_bytes() + b"synthetic-changed")
    else:
        fields: dict[str, Any] = {"pg_restore_sha256": "a" * 64}
        if kind == "prefix8":
            fields = {"source_migrations": sample.inputs.release.migrations}
        elif kind == "candidate":
            fields = {"candidate": "b" * 40}
        inputs = replace(inputs, dump_pin=replace(inputs.dump_pin, **fields))
    with pytest.raises(RestoreRejected):
        execute(inputs, apply_local=True, environment=sample.environment)
    assert sample.present() == (False, 0)


@pytest.mark.parametrize("sample", [8], indirect=True)
def test_actual_central_ledger_archive_is_refused_before_role_or_database_creation(sample):
    with pytest.raises(RestoreRejected, match="CENTRAL_LEDGER_ARCHIVE_REJECTED"):
        execute(sample.inputs, apply_local=True, environment=sample.environment)
    assert sample.present() == (False, 0)


def test_actual_restore_error_retains_new_database_and_roles_without_second_restore(sample):
    with psycopg.connect(sample.source) as source:
        source.execute(
            "CREATE FUNCTION public.synthetic_event() RETURNS event_trigger LANGUAGE plpgsql AS $$ BEGIN NULL; END $$"
        )
        source.execute(
            "CREATE EVENT TRIGGER synthetic_privileged_event ON ddl_command_start "
            "EXECUTE FUNCTION public.synthetic_event()"
        )
    sample.dump()
    with pytest.raises(RestoreRejected, match="LOCAL_PG_RESTORE_PROCESS_FAILED"):
        execute(sample.inputs, apply_local=True, environment=sample.environment)
    assert sample.present() == (True, 2)
    with psycopg.connect(sample.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
        assert owner.execute("SELECT to_regnamespace('mingjing_core') IS NULL").fetchone() == (True,)
    with pytest.raises(RestoreRejected, match="ALREADY_EXISTS"):
        execute(sample.inputs, apply_local=True, environment=sample.environment)
    assert sample.present() == (True, 2)


def test_wrong_declared_original_prefix_stops_after_restore_and_preserves_evidence(sample):
    inputs = replace(
        sample.inputs,
        dump_pin=replace(
            sample.inputs.dump_pin,
            source_migrations=tuple((str(v), dict(sample.inputs.release.migrations)[str(v)]) for v in range(1, 8)),
        ),
    )
    with pytest.raises(RestoreRejected, match="RESTORED_ORIGINAL_PREFIX_MISMATCH"):
        execute(inputs, apply_local=True, environment=sample.environment)
    assert sample.present() == (True, 2)


def test_cli_public_failure_never_echoes_process_credentials_or_private_body(sample, monkeypatch, capsys):
    workspace = sample.inputs.workspace
    write_json(workspace / "pin.json", pin_document(sample.inputs.release))
    write_json(workspace / "contract.json", contract_document(sample.inputs.contract))
    pin = sample.inputs.dump_pin
    write_json(
        workspace / "dump-pin.json",
        {
            "schema": "first-release-local-dump-pin-v1",
            "candidate": pin.candidate,
            "manifest_sha256": pin.manifest_sha256,
            "dump_sha256": pin.dump_sha256,
            "pg_restore_sha256": pin.pg_restore_sha256,
            "source_migrations": dict(pin.source_migrations),
        },
    )
    monkeypatch.chdir(workspace)
    for key, value in sample.environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PGOPTIONS", "-c role=SYNTHETIC_SECRET")
    files = {
        "pin": workspace / "pin.json",
        "contract": workspace / "contract.json",
        "dump-pin": workspace / "dump-pin.json",
        "dump": sample.inputs.dump,
        "pg-restore": sample.inputs.pg_restore,
    }
    arguments = [item for name, path in files.items() for item in ("--" + name, str(path))]
    assert main([*arguments, "--apply-local"]) == 2
    output = capsys.readouterr().out
    assert "IMPLICIT_PG_REJECTED" in output
    assert "SYNTHETIC_SECRET" not in output and PRIVATE not in output and "postgresql://" not in output


@pytest.mark.parametrize("kind", ["occupied", "changed_owner"])
def test_new_public_initialization_refuses_changed_default_and_preserves_it(sample, monkeypatch, kind):
    from tools import first_release_local_pg

    original = first_release_local_pg.initialize_public

    def changed(inputs, dsns):
        target = make_conninfo(dsns["admin"], dbname=inputs.contract.database)
        with psycopg.connect(target) as admin:
            if kind == "occupied":
                admin.execute("CREATE TABLE public.synthetic_occupied(id integer)")
            else:
                admin.execute(
                    sql.SQL("ALTER SCHEMA public OWNER TO {}").format(
                        sql.Identifier(conninfo_to_dict(dsns["admin"])["user"])
                    )
                )
        original(inputs, dsns)

    monkeypatch.setattr(first_release_local_pg, "initialize_public", changed)
    with pytest.raises(RestoreRejected, match="NEW_LOCAL_PUBLIC_NOT_EMPTY_DEFAULT"):
        execute(sample.inputs, apply_local=True, environment=sample.environment)
    assert sample.present() == (True, 2)
    with psycopg.connect(make_conninfo(sample.admin, dbname=sample.inputs.contract.database)) as admin:
        assert admin.execute("SELECT to_regnamespace('mingjing_core') IS NULL").fetchone() == (True,)
        assert admin.execute("SELECT to_regclass('public.synthetic_occupied') IS NOT NULL").fetchone() == (
            kind == "occupied",
        )


def scram_matches(verifier: str, password: str) -> bool:
    scheme, parameters, keys = verifier.split("$")
    rounds, salt = parameters.split(":")
    stored, server = keys.split(":")
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(rounds))
    return (
        scheme == "SCRAM-SHA-256"
        and hashlib.sha256(hmac.digest(salted, b"Client Key", "sha256")).digest() == base64.b64decode(stored)
        and hmac.digest(salted, b"Server Key", "sha256") == base64.b64decode(server)
    )


def test_role_sql_uses_client_scram_verifiers_with_actual_ddl_logging(sample, monkeypatch):
    fields = [conninfo_to_dict(sample.environment["FIRST_RELEASE_" + role + "_DSN"]) for role in ("OWNER", "WRITER")]
    original = psycopg.Connection.execute
    checked = []

    def inspect(connection, query, *args, **kwargs):
        statement = query.as_string(connection) if isinstance(query, sql.Composable) else query
        if isinstance(statement, str) and statement.startswith("CREATE ROLE "):
            if "SCRAM-SHA-256$" not in statement or any(item["password"] in statement for item in fields):
                raise AssertionError("ROLE_DDL_PASSWORD_BOUNDARY")
            original(connection, "SET log_statement='ddl'")
            checked.append(True)
        return original(connection, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "execute", inspect)
    result = execute(sample.inputs, apply_local=True, environment=sample.environment)
    assert checked == [True, True], "TWO_ROLE_DDL_STATEMENTS_REQUIRED"
    for item in fields:
        with psycopg.connect(sample.admin) as admin:
            row = admin.execute("SELECT rolpassword FROM pg_authid WHERE rolname=%s", (item["user"],)).fetchone()
        verifier = row[0]
        assert scram_matches(verifier, item["password"]), "SCRAM_VERIFIER_PASSWORD_MISMATCH"
        assert verifier not in json.dumps(result) and item["password"] not in json.dumps(result), "RECEIPT_SECRET"
        with psycopg.connect(make_conninfo(**item)) as role:
            assert role.execute("SELECT current_user").fetchone()[0] == item["user"], "ACTUAL_ROLE_LOGIN_FAILED"

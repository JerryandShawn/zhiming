"""Create only a new F writer/config/unit asset; explicit admission affects only the new copy."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from tools.first_release_contracts import RestoreRejected, digest, ordinary, read_json, require
from tools.first_release_database_metadata import capture
from tools.first_release_migration_steps import grant_new_runtime
from tools.first_release_native_exchange import Scope, _environment, control, file_hash, write_private
from tools.first_release_restore import SafeParser
from tools.first_release_stage_backup import _closed_empty
from tools.first_release_writer_fence import file_lock


def unit(candidate: str, operation: str) -> bytes:
    require(digest(candidate, 40) and digest(operation, 16), "STAGE_UNIT_PIN_REQUIRED")
    root = "/root/zhiming-core-fr-stage"
    release, workspace = f"{root}/releases/{candidate}", f"{root}/operations/{operation}"
    command = f"{root}/venvs/{candidate}/core/bin/python -I {release}/tools/first_release_stage_app.py"
    return (
        f"""[Unit]
Description=Zhiming first-release copy health-only stage
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory={release}
ExecStart={command} --env-file {workspace}/runtime.json
Restart=no
KillSignal=SIGTERM
TimeoutStopSec=45
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={workspace}
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
IPAddressDeny=any
IPAddressAllow=127.0.0.0/8 ::1/128
SocketBindDeny=any
SocketBindAllow=ipv4:tcp:8788
UnsetEnvironment=KIMI_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN MEMBER_CENTRAL_DSN
UnsetEnvironment=HTTP_PROXY HTTPS_PROXY ALL_PROXY
StandardOutput=journal
StandardError=journal
"""
    ).encode()


def _workspace(scope: Scope, workspace: Path) -> None:
    scope.validate()
    ordinary(workspace, directory=True)
    require(
        scope.local_drill or workspace == Path("/root/zhiming-core-fr-stage/operations") / scope.operation,
        "STAGE_DEDICATED_WORKSPACE_REQUIRED",
    )
    require(scope.local_drill or workspace.stat().st_mode & 0o077 == 0, "STAGE_PRIVATE_WORKSPACE")


def provision(
    scope: Scope, workspace: Path, exchanged: dict, candidate: str, tokenizer: Path, *, environment=None
) -> dict:
    _workspace(scope, workspace)
    require(digest(candidate, 40), "STAGE_CANDIDATE_REQUIRED")
    ordinary(tokenizer, directory=True)
    require(
        exchanged.get("status") == "exchanged_closed"
        and exchanged.get("operation") == scope.operation
        and exchanged.get("admission_opened") is False,
        "STAGE_EXCHANGE_RECEIPT_REQUIRED",
    )
    role = scope.original + "_writer"
    with file_lock(workspace / "writer.lock", exclusive=True), control(scope, environment) as (admin, dsn):
        require(
            not any(
                os.path.lexists(workspace / name)
                for name in (
                    "runtime-started.json",
                    "runtime.json",
                    "runtime-receipt.json",
                    "zhiming-core-fr-stage.service",
                )
            ),
            "STAGE_RUNTIME_ALREADY_STARTED_NO_RETRY",
        )
        require(
            admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone() is None,
            "STAGE_NEW_WRITER_REQUIRED",
        )
        metadata = capture(admin, scope.original)
        require(metadata["oid"] == exchanged.get("current_oid"), "STAGE_EXCHANGED_DATABASE_CHANGED")
        _closed_empty(admin, scope, metadata)
        write_private(
            workspace / "runtime-started.json", {"operation": scope.operation, "database_oid": metadata["oid"]}
        )
        runtime_dsn, role_oid = _new_writer(admin, dsn, scope, role)
    return _assets(scope, workspace, candidate, tokenizer, metadata, role, role_oid, runtime_dsn)


def _new_writer(admin, dsn: str, scope: Scope, role: str) -> tuple[str, int]:
    password = secrets.token_urlsafe(32)
    verifier = admin.pgconn.encrypt_password(password.encode(), role.encode(), b"scram-sha-256").decode()
    require(verifier.startswith("SCRAM-SHA-256$"), "STAGE_SCRAM_VERIFIER_REQUIRED")
    admin.execute(
        sql.SQL(
            "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 3 PASSWORD {}"
        ).format(sql.Identifier(role), sql.Literal(verifier))
    )
    _grant(admin, dsn, scope, role)
    _closed_empty(admin, scope, capture(admin, scope.original))
    fields = conninfo_to_dict(dsn)
    runtime_dsn = make_conninfo(
        host=fields["host"],
        port=fields["port"],
        dbname=scope.original,
        user=role,
        password=password,
        connect_timeout="5",
    )
    role_oid = admin.execute("SELECT oid FROM pg_roles WHERE rolname=%s", (role,)).fetchone()["oid"]
    return runtime_dsn, role_oid


def _assets(scope, workspace, candidate, tokenizer, metadata, role, role_oid, runtime_dsn) -> dict:
    config = workspace / "runtime.json"
    write_private(
        config,
        dict(
            dsn=runtime_dsn,
            token=secrets.token_urlsafe(32),
            operation=scope.operation,
            database_oid=metadata["oid"],
            workspace=str(workspace),
            tokenizer=str(tokenizer),
        ),
    )
    content = unit(candidate, scope.operation)
    descriptor = os.open(workspace / "zhiming-core-fr-stage.service", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
    result = dict(
        schema="first-release-stage-runtime-v1",
        status="provisioned_closed",
        operation=scope.operation,
        candidate=candidate,
        database_oid=metadata["oid"],
        writer=role,
        writer_oid=role_oid,
        config_sha256=file_hash(config),
        unit_sha256=file_hash(workspace / "zhiming-core-fr-stage.service"),
        admission_opened=False,
        unit_installed=False,
        model_calls=0,
        external_sends=0,
        automatic_retry=False,
    )
    write_private(workspace / "runtime-receipt.json", result)
    return result


def _grant(admin, dsn: str, scope: Scope, role: str) -> None:
    admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(scope.original)))
    with psycopg.connect(make_conninfo(dsn, dbname=scope.original), row_factory=dict_row) as target:
        grant_new_runtime(target, role)
    admin.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path=public,pg_catalog").format(
            sql.Identifier(role), sql.Identifier(scope.original)
        )
    )
    admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(scope.original)))


def admit(scope: Scope, workspace: Path, receipt: dict, *, environment=None) -> dict:
    _workspace(scope, workspace)
    require(
        receipt.get("schema") == "first-release-stage-runtime-v1"
        and receipt.get("status") == "provisioned_closed"
        and receipt.get("operation") == scope.operation
        and receipt.get("writer") == scope.original + "_writer",
        "STAGE_RUNTIME_RECEIPT_REQUIRED",
    )
    require(file_hash(workspace / "runtime.json") == receipt.get("config_sha256"), "STAGE_RUNTIME_CONFIG_CHANGED")
    with file_lock(workspace / "writer.lock", exclusive=True), control(scope, environment) as (admin, _):
        require(
            not os.path.lexists(workspace / "maintenance.json")
            and not os.path.lexists(workspace / "admitted-receipt.json"),
            "STAGE_ADMISSION_NOT_NEW_OR_MAINTENANCE",
        )
        metadata = capture(admin, scope.original)
        require(metadata["oid"] == receipt.get("database_oid"), "STAGE_RUNTIME_DATABASE_CHANGED")
        _closed_empty(admin, scope, metadata)
        role = admin.execute("SELECT oid FROM pg_roles WHERE rolname=%s", (receipt["writer"],)).fetchone()
        require(role and role["oid"] == receipt.get("writer_oid"), "STAGE_RUNTIME_WRITER_CHANGED")
        admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(scope.original)))
    result = dict(
        status="copy_database_admitted",
        operation=scope.operation,
        database_oid=metadata["oid"],
        unit_started=False,
        model_calls=0,
        external_sends=0,
        automatic_retry=False,
    )
    write_private(workspace / "admitted-receipt.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("provision", "admit"))
    parser.add_argument("--operation", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--tokenizer", type=Path)
    parser.add_argument("--admin-env-file", type=Path)
    parser.add_argument("--local-drill", action="store_true")
    parser.add_argument("--apply", action="store_true")
    try:
        args = parser.parse_args(argv)
        scope = Scope(args.operation, args.local_drill)
        scope.validate()
        if not args.apply:
            print(json.dumps({"status": "arguments_validated", "database_connections": 0, "model_calls": 0}))
            return 0
        require(file_hash(args.receipt) == args.receipt_sha256, "STAGE_RUNTIME_INPUT_CHANGED")
        environment = _environment(scope, args.admin_env_file)
        receipt = read_json(args.receipt)
        result = (
            provision(scope, args.workspace, receipt, args.candidate, args.tokenizer, environment=environment)
            if args.action == "provision"
            else admit(scope, args.workspace, receipt, environment=environment)
        )
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_retry": False}))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "STAGE_RUNTIME_STOP_PRESERVE_ALL", "automatic_retry": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

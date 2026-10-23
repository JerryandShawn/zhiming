"""Read-only native candidate export, importing the parent's live PostgreSQL snapshot."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import runpy
import sys
from pathlib import Path
from typing import Any


class ExportBlocked(RuntimeError):
    """Only fixed codes are emitted; raw database/provider exceptions never cross the pipe."""


def require(value: Any, code: str) -> None:
    if not value:
        raise ExportBlocked(code)


def foundation(value: dict[str, Any]) -> dict[str, Any]:
    path = Path(value["worker"]).with_name("first_release_replay_worker.py")
    require(
        path == Path(value["foundation"])
        and path.is_file()
        and not any(item.is_symlink() for item in (path, *path.parents)),
        "INCREMENTAL_FOUNDATION_PATH",
    )
    require(
        hashlib.sha256(path.read_bytes()).hexdigest() == value["controls"][path.name],
        "INCREMENTAL_FOUNDATION_CHANGED",
    )
    require(
        not any(name.split(".")[0] in {"tools", "mingjing_core"} for name in sys.modules),
        "INCREMENTAL_PRELOADED_BUSINESS",
    )
    return runpy.run_path(str(path))


def candidate(value: dict[str, Any], base: dict[str, Any]) -> tuple[Any, Any, Any]:
    root = Path(value["root"])
    raw = (root / "__release_manifest__.json").read_bytes()
    require(
        hashlib.sha256(raw).hexdigest() == value["pin"]["manifest_sha256"],
        "INCREMENTAL_MANIFEST_CHANGED",
    )
    manifest = json.loads(raw)
    require(manifest["commit"] == value["pin"]["candidate"], "INCREMENTAL_CANDIDATE_CHANGED")
    files = manifest["files"]
    sys.meta_path.insert(0, base["CandidateFinder"](root, files))
    sys.path.insert(0, str(root))
    sites, installed = base["runtime"](value, root)
    repository = importlib.import_module("mingjing_core.repositories.postgres")
    deployment = importlib.import_module("tools.deploy_core")
    for function in (
        deployment.export_withdrawals,
        repository.PostgresRepository.export_privacy,
    ):
        base["verified"](function.__code__.co_filename, root, files)

    def audit() -> None:
        base["third_party_origins"](sites)
        base["business_origins"](root, files)

    audit()
    return repository, deployment, audit


def owner_fields(source: dict[str, Any]) -> dict[str, str]:
    from psycopg.conninfo import conninfo_to_dict

    fields = conninfo_to_dict(os.environ.get("FIRST_INCREMENTAL_OWNER_DSN", ""))
    require(
        not any(key.startswith("PG") and item for key, item in os.environ.items()),
        "INCREMENTAL_IMPLICIT_PG",
    )
    require(
        set(fields)
        <= {
            "host",
            "hostaddr",
            "port",
            "dbname",
            "user",
            "password",
            "passfile",
            "connect_timeout",
        }
        and fields.get("host") in {"127.0.0.1", "::1"}
        and fields.get("port") in {"55480", "55481"},
        "INCREMENTAL_WORKER_DSN",
    )
    require(
        fields.get("dbname") == source["database"]
        and fields.get("user") == source["database"] + "_owner"
        and fields.get("hostaddr", fields["host"]) == fields["host"]
        and fields.get("passfile", os.devnull) == os.devnull,
        "INCREMENTAL_WORKER_ROLE",
    )
    return fields


def export(value: dict[str, Any], repository: Any, deployment: Any, audit: Any) -> dict[str, Any]:
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    source = value["source"]
    fields = owner_fields(source)
    require(re.fullmatch(r"[0-9A-Fa-f-]{8,80}", value["snapshot"]), "INCREMENTAL_SNAPSHOT_FORMAT")
    dsn = make_conninfo(
        **fields,
        options="-c default_transaction_read_only=on -c search_path=pg_catalog",
    )
    repo = repository.PostgresRepository(dsn, initialize=False, max_size=1)
    try:
        with repo.transaction() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute(sql.SQL("SET TRANSACTION SNAPSHOT {}").format(sql.Literal(value["snapshot"])))
            pid = connection.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
            print(
                json.dumps(
                    {
                        "schema": "first-release-incremental-export-handshake-v1",
                        "pid": pid,
                    }
                ),
                flush=True,
            )
            require(
                json.loads(sys.stdin.readline()) == {"pid": pid},
                "INCREMENTAL_HANDSHAKE_ACK",
            )
            verify_source(connection, source, fields)
            audit()
            document = deployment.export_withdrawals(repo)
            audit()
        return {
            "schema": "first-release-incremental-export-v1",
            "pid": pid,
            "snapshot": value["snapshot"],
            "candidate": value["pin"]["candidate"],
            "document": document,
            "read_only": True,
            "runtime_verified": False,
            "publication": False,
        }
    finally:
        repo.close()


def verify_source(connection: Any, source: dict[str, Any], fields: dict[str, str]) -> None:
    actual = connection.execute(
        "SELECT current_database() AS database,current_user AS role,session_user AS session_role,"
        "host(inet_server_addr()) AS host,inet_server_port() AS port,"
        "current_setting('server_version_num')::int AS version,"
        "(SELECT oid FROM pg_database WHERE datname=current_database()) AS oid,"
        "(SELECT oid FROM pg_roles WHERE rolname=current_user) AS role_oid,"
        "current_setting('transaction_read_only') AS readonly,current_setting('transaction_isolation') AS isolation"
    ).fetchone()
    require(
        (
            actual["database"],
            actual["role"],
            actual["session_role"],
            actual["host"],
            str(actual["port"]),
        )
        == (
            source["database"],
            fields["user"],
            fields["user"],
            fields["host"],
            fields["port"],
        )
        and actual["oid"] == source["database_oid"]
        and actual["role_oid"] == source["owner_oid"]
        and 150000 <= actual["version"] < 160000
        and actual["readonly"] == "on"
        and actual["isolation"] == "repeatable read",
        "INCREMENTAL_WORKER_ACTUAL_IDENTITY",
    )
    history = connection.execute(
        "SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version"
    ).fetchall()
    require(
        {str(row["version"]): row["checksum"] for row in history} == dict(source["migrations"]),
        "INCREMENTAL_WORKER_PREFIX",
    )
    owners = sorted(row["id"] for row in connection.execute("SELECT id FROM mingjing_core.core_owners"))
    require(owners == source["owners"], "INCREMENTAL_WORKER_OWNER_SET")


if __name__ == "__main__":
    try:
        payload = globals().get("_INCREMENTAL_INPUT")
        shared = foundation(payload)
        result = export(payload, *candidate(payload, shared))
    except Exception as error:
        code = str(error) if isinstance(error, ExportBlocked) else "INCREMENTAL_READONLY_EXPORT_FAILED"
        result = {"status": "blocked", "code": code}
    print(json.dumps(result, sort_keys=True), flush=True)
    raise SystemExit(2 if result.get("status") == "blocked" else 0)

"""Run only the pinned candidate's replay code against the isolated stage restore DB."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from typing import Any

from psycopg import sql

from tools.b1_restore_replay_contracts import (
    DATABASE,
    MIGRATIONS,
    RestoreRequest,
    require,
)


def preflight(repo: Any, connection: Any, request: RestoreRequest, owners: set[str]) -> dict[str, Any]:
    connection.execute("SET LOCAL statement_timeout='5s'")
    identity = connection.execute(
        "SELECT current_database() AS database,current_user AS role,host(inet_server_addr()) AS host,"
        "inet_server_port() AS port,current_setting('server_version_num')::int AS version_num"
    ).fetchone()
    require(
        identity["database"] == DATABASE and identity["role"] == DATABASE + "_owner",
        "RESTORE_IDENTITY",
    )
    require(150000 <= identity["version_num"] < 160000, "POSTGRES15_REQUIRED")
    if not request.local_drill:
        require(
            identity["host"] in {"127.0.0.1", "::1"} and identity["port"] == 5432,
            "SERVER_LOOPBACK_ONLY",
        )
    role = connection.execute(
        "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"
    ).fetchone()
    require(not any(role.values()), "MIGRATION_ROLE_ELEVATED")
    owner = connection.execute(
        "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname=current_database()"
    ).fetchone()["owner"]
    require(owner == DATABASE + "_owner", "DATABASE_OWNER")
    checksums = {
        str(row["version"]): row["checksum"]
        for row in connection.execute(
            sql.SQL("SELECT version,checksum FROM {} ORDER BY version").format(repo.table("schema_migrations"))
        ).fetchall()
    }
    require(checksums == MIGRATIONS, "RESTORE_SCHEMA7_CHECKSUMS")
    actual = {row["id"] for row in connection.execute(sql.SQL("SELECT id FROM {}").format(repo.table("core_owners")))}
    require(actual == owners, "COMPLETE_OWNER_LEDGER_REQUIRED")
    queues = connection.execute(
        sql.SQL(
            "SELECT count(*) FILTER(WHERE status IN ('queued','running')) AS active,"
            "count(*) FILTER(WHERE lease_until>now()) AS leases FROM {}"
        ).format(repo.table("core_runs"))
    ).fetchone()
    require(queues == {"active": 0, "leases": 0}, "RESTORE_NOT_QUIESCENT")
    sessions = connection.execute(
        "SELECT count(*) AS count FROM pg_stat_activity WHERE datname=current_database() "
        "AND pid<>pg_backend_pid() AND backend_type='client backend'"
    ).fetchone()["count"]
    require(sessions == 0, "OTHER_RESTORE_SESSIONS")
    locked = connection.execute(
        "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS locked",
        (DATABASE + ":b1-stage-restore-replay",),
    ).fetchone()["locked"]
    require(locked, "RESTORE_REPLAY_LOCKED")
    return {
        "checksums": checksums,
        "postgres_major": 15,
        "server_loopback_verified": identity["host"] in {"127.0.0.1", "::1"},
    }


def state_hash(repo: Any, connection: Any) -> str:
    tables = connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename",
        (repo.schema,),
    ).fetchall()
    hashes = []
    for row in tables:
        value = connection.execute(
            sql.SQL(
                "SELECT coalesce(md5(string_agg(md5(to_jsonb(t)::text),'' "
                "ORDER BY md5(to_jsonb(t)::text))),md5('')) AS value FROM {} t"
            ).format(repo.table(row["tablename"]))
        ).fetchone()["value"]
        hashes.append(row["tablename"] + ":" + value)
    return hashlib.sha256("\n".join(hashes).encode()).hexdigest()


def replay(request: RestoreRequest, document: dict[str, Any]) -> dict[str, Any]:
    # Fresh process import ordering is deliberate: current development business
    # modules cannot be substituted for the immutable B1 candidate.
    repository = importlib.import_module("mingjing_core.repositories.postgres")
    deployment = importlib.import_module("tools.deploy_core")
    root = request.candidate_source.resolve()
    for module in (repository, deployment):
        require(
            Path(module.__file__).resolve().is_relative_to(root),
            "WRONG_CANDIDATE_IMPORT",
        )
    repo = repository.PostgresRepository(request.dsn(), schema=request.schema, initialize=False, max_size=2)
    try:
        with repo.transaction() as connection:
            identity = preflight(
                repo,
                connection,
                request,
                {row["owner_user_id"] for row in document["owners"]},
            )
            repo.verify_schema()
            before = state_hash(repo, connection)
            result = deployment.apply_withdrawals(repo, document)
            after = state_hash(repo, connection)
        return {
            "schema": "b1-stage-restore-replay-v1",
            "operation_id": request.operation_id,
            "database": DATABASE,
            "target": "b9a89b6f84f7bebb640de080548010859aae630c",
            "ledger_sha256": request.ledger_sha256,
            "changed": before != after,
            "state_before_sha256": before,
            "state_after_sha256": after,
            "counts": result,
            **identity,
            "model_calls": 0,
            "external_sends": 0,
        }
    finally:
        repo.close()

"""Exercise only fixed-b9 primary backfill on an exact synthetic source fixture."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from tools.b1_linux_application_drill_contracts import ApplicationRequest, require
from tools.b1_restore_proof_pg import state_hash
from tools.core_incremental_contracts import MIGRATIONS, digest


def modules(request: ApplicationRequest) -> tuple[Any, Any, Any]:
    values = tuple(
        importlib.import_module(name)
        for name in (
            "mingjing_core.repositories.postgres",
            "mingjing_core.application.memory",
            "mingjing_core.memory.backfill",
        )
    )
    for value in values:
        require(
            Path(value.__file__).resolve().is_relative_to(request.candidate_source.resolve()), "WRONG_CANDIDATE_IMPORT"
        )
    return values


def synthetic_fixture(conn: Any) -> None:
    require(
        {row["id"] for row in conn.execute("SELECT id FROM mingjing_core.core_owners")} == {"primary", "secondary"},
        "SYNTHETIC_APPLICATION_FIXTURE_REQUIRED",
    )
    rows = conn.execute(
        "SELECT owner,kind,id,revision,status,data FROM mingjing_core.core_entities ORDER BY owner,id"
    ).fetchall()
    reply_id = "msg_" + digest(["primary", "assistant", "synthetic-run"])[:32]
    allowed = {
        ("primary", "message", "synthetic-message"),
        ("secondary", "message", "synthetic-secondary"),
        ("primary", "message", reply_id),
    }
    actual = {(row["owner"], row["kind"], row["id"]) for row in rows}
    require(
        actual <= allowed and {item for item in allowed if item[2] != reply_id} <= actual,
        "SYNTHETIC_APPLICATION_ENTITIES_REQUIRED",
    )
    require(
        all(row["status"] == "active" and row["revision"] == 1 for row in rows),
        "SYNTHETIC_APPLICATION_ENTITIES_REQUIRED",
    )
    bodies = {row["id"]: row["data"] for row in rows}
    require(
        bodies["synthetic-message"].get("content") == "synthetic original"
        and bodies["synthetic-message"].get("role") == "user"
        and bodies["synthetic-secondary"].get("content") == "synthetic untouched",
        "SYNTHETIC_APPLICATION_ENTITIES_REQUIRED",
    )
    require(
        {row["id"] for row in conn.execute("SELECT id FROM mingjing_core.core_runs")} == {"synthetic-run"},
        "SYNTHETIC_APPLICATION_RUNS_REQUIRED",
    )
    run = conn.execute(
        "SELECT request,result,status FROM mingjing_core.core_runs WHERE id='synthetic-run' AND owner='primary'"
    ).fetchone()
    require(
        run
        and run["status"] == "succeeded"
        and run["request"].get("source_message_id") == "synthetic-message"
        and run["result"] == {"answer": "SYNTHETIC_B1_LEGACY_REPLY"},
        "SYNTHETIC_APPLICATION_FIXTURE_REQUIRED",
    )


def preflight(repo: Any, conn: Any, request: ApplicationRequest) -> None:
    row = conn.execute(
        "SELECT current_database() AS db,current_user AS role,host(inet_server_addr()) AS host,"
        "inet_server_port() AS port,current_setting('server_version_num')::int AS version,version() AS build"
    ).fetchone()
    require(row["role"] == row["db"] + "_owner" and row["host"] in {"127.0.0.1", "::1"}, "APPLICATION_IDENTITY")
    fields = conninfo_to_dict(request.dsn())
    require(row["db"] == fields["dbname"] and row["port"] == int(fields["port"]), "APPLICATION_IDENTITY")
    require(
        150000 <= row["version"] < 160000 and (request.local_drill or "linux" in row["build"].lower()),
        "APPLICATION_PG15",
    )
    role = conn.execute(
        "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR "
        "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user))"
        " AS elevated FROM pg_roles WHERE rolname=current_user"
    ).fetchone()
    require(role and not role["elevated"], "APPLICATION_ROLE_ELEVATED")
    owner = conn.execute(
        "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname=current_database()"
    ).fetchone()["owner"]
    require(owner == row["role"], "APPLICATION_DATABASE_OWNER")
    require(
        {
            str(row["version"]): row["checksum"]
            for row in conn.execute("SELECT version,checksum FROM mingjing_core.schema_migrations")
        }
        == MIGRATIONS,
        "APPLICATION_SCHEMA7",
    )
    synthetic_fixture(conn)
    busy = conn.execute(
        "SELECT count(*) FILTER(WHERE status IN ('queued','running') OR lease_until>now()) AS n "
        "FROM mingjing_core.core_runs"
    ).fetchone()["n"]
    require(busy == 0, "APPLICATION_QUEUE_NOT_QUIESCENT")
    sessions = conn.execute(
        "SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() "
        "AND pid<>pg_backend_pid() AND backend_type='client backend'"
    ).fetchone()["n"]
    require(sessions == 0, "APPLICATION_OTHER_SESSIONS")


def immutable(repository: Any, conn: Any, owner: str) -> dict:
    rows = conn.execute(
        "SELECT kind,id,subject,case_id,status,revision,created_at,updated_at,"
        "data-'search_tokens'-'thread_id'-'at_ms'-'origin_conversation_id' AS original "
        "FROM mingjing_core.core_entities WHERE owner=%s ORDER BY kind,id",
        (owner,),
    ).fetchall()
    return {(row["kind"], row["id"]): repository.fingerprint(row) for row in rows}


def frozen_tables(conn: Any, *, lock: bool = False) -> dict[str, str]:
    tables = conn.execute(
        "SELECT schemaname,tablename FROM pg_tables WHERE schemaname='mingjing_core' OR "
        "schemaname='public' AND tablename IN ('checkpoints','checkpoint_blobs','checkpoint_writes',"
        "'checkpoint_migrations') ORDER BY schemaname,tablename"
    ).fetchall()
    hashes = {}
    for row in tables:
        table = sql.Identifier(row["schemaname"], row["tablename"])
        if lock:
            conn.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(table))
        if row["schemaname"] == "mingjing_core" and row["tablename"] in {"core_entities", "core_operations"}:
            continue
        projection = (
            sql.SQL("CASE WHEN id='primary' THEN to_jsonb(t)-'revision' ELSE to_jsonb(t) END")
            if row["tablename"] == "core_owners"
            else sql.SQL("to_jsonb(t)")
        )
        query = sql.SQL(
            "SELECT encode(sha256(convert_to(coalesce(jsonb_agg({} ORDER BY to_jsonb(t)::text),"
            "'[]'::jsonb)::text,'UTF8')),'hex') AS hash FROM {} t"
        ).format(projection, table)
        hashes[row["schemaname"] + "." + row["tablename"]] = conn.execute(query).fetchone()["hash"]
    return hashes


def backfill_primary(request: ApplicationRequest) -> dict[str, Any]:
    repository, application, business = modules(request)
    repo = repository.PostgresRepository(request.dsn(), initialize=False, max_size=1)
    try:
        with repo.transaction("primary") as conn:
            preflight(repo, conn, request)
            frozen = frozen_tables(conn, lock=True)
            owner_revision = conn.execute(
                "SELECT revision FROM mingjing_core.core_owners WHERE id='primary'"
            ).fetchone()["revision"]
            original, secondary = immutable(repository, conn, "primary"), immutable(repository, conn, "secondary")
            before = state_hash(conn)
            dry = business.backfill(application.MemoryService(repo), "primary", apply=False)
            require(state_hash(conn) == before, "APPLICATION_DRY_RUN_WROTE")
            first = business.backfill(application.MemoryService(repo), "primary", apply=True)
            second = business.backfill(application.MemoryService(repo), "primary", apply=True)
            keys = ("message_metadata", "search_tokens", "assistant_created")
            require(
                all(type(first.get(key)) is int and first[key] > 0 for key in keys), "APPLICATION_FIRST_APPLY_VACUOUS"
            )
            require(
                all(type(second.get(key)) is int and second[key] == 0 for key in keys), "APPLICATION_REPEAT_CHANGED"
            )
            after = immutable(repository, conn, "primary")
            require(all(after.get(key) == value for key, value in original.items()), "APPLICATION_ORIGINAL_CHANGED")
            require(immutable(repository, conn, "secondary") == secondary, "APPLICATION_OTHER_OWNER_CHANGED")
            require(frozen_tables(conn) == frozen, "APPLICATION_NON_BACKFILL_TABLE_CHANGED")
            current = conn.execute("SELECT revision FROM mingjing_core.core_owners WHERE id='primary'").fetchone()[
                "revision"
            ]
            require(current == owner_revision + first["assistant_created"], "APPLICATION_OWNER_REVISION_CHANGED")
            final = state_hash(conn)
        for value in (dry, first, second):
            value["sample_ids"] = [digest(ident) for ident in value.get("sample_ids", [])]
        return {
            "owner": "primary",
            "dry": dry,
            "first": first,
            "repeat": second,
            "state_before_sha256": before,
            "state_after_sha256": final,
            "originals_preserved": True,
            "other_owner_preserved": True,
            "candidate_business_verified": True,
            "non_backfill_tables_preserved": True,
        }
    finally:
        repo.close()

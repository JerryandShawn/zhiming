"""Private opt-in forward stage for the fresh, still-locked local restore target."""

from __future__ import annotations

import hashlib
from typing import Any

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.foundation import validate_history
from mingjing_core.repositories.permissions import grant_runtime_tables
from tools.b1_restore_proof_worker import grant_checkpoints
from tools.first_release_acl import QUOTA, verify_database_acl
from tools.first_release_contracts import RestoreRejected, ordinary, require
from tools.first_release_local_inputs import LocalInputs
from tools.first_release_local_pg import server_identity
from tools.first_release_source import MIGRATION_DIR


def _require_creator(inputs: LocalInputs, dsns: dict[str, str], creator: Any) -> None:
    require(isinstance(creator, psycopg.Connection) and not creator.closed, "LOCAL_UPGRADE_FRESH_CREATOR_REQUIRED")
    server_identity(creator, conninfo_to_dict(dsns["admin"]))
    row = creator.execute(
        "WITH key AS (SELECT hashtextextended(%s,0) AS value) "
        "SELECT current_setting('search_path')='pg_catalog' AND EXISTS("
        "SELECT 1 FROM pg_locks,key WHERE locktype='advisory' AND pid=pg_backend_pid() AND granted "
        "AND classid::bigint=((key.value>>32)&4294967295) "
        "AND objid::bigint=(key.value&4294967295) AND objsubid=1) AS locked",
        ("first-release-local:" + inputs.contract.database,),
    ).fetchone()
    require(row["locked"], "LOCAL_UPGRADE_FRESH_CREATOR_LOCK_REQUIRED")


def _sources(inputs: LocalInputs) -> dict[int, str]:
    # Revalidate the reviewed candidate after restore; never scan the controller's migration package.
    inputs.validate()
    expected = {int(version): checksum for version, checksum in inputs.release.migrations}
    result = {}
    for path in sorted((inputs.contract.candidate_source / MIGRATION_DIR).glob("[0-9][0-9][0-9][0-9]_*.sql")):
        ordinary(path)
        version = int(path.name[:4])
        source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        require(version not in result and version in expected, "LOCAL_UPGRADE_MIGRATION_SET")
        require(hashlib.sha256(source.encode()).hexdigest() == expected[version], "LOCAL_UPGRADE_SQL_CHANGED")
        result[version] = source
    require(set(result) == set(range(1, 9)), "LOCAL_UPGRADE_EXACT_1_8_REQUIRED")
    return result


def _history(connection: Any) -> dict[int, str]:
    return {
        row["version"]: row["checksum"]
        for row in connection.execute("SELECT version,checksum FROM mingjing_core.schema_migrations").fetchall()
    }


def _migrate(connection: Any, inputs: LocalInputs, sources: dict[int, str]) -> list[int]:
    expected = {int(version): checksum for version, checksum in inputs.release.migrations}
    try:
        with connection.transaction():
            connection.execute("SET LOCAL search_path=pg_catalog")
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('mingjing_core:schema',0))")
            actual = _history(connection)
            validate_history(actual, expected, complete=False)
            require(
                actual == {int(version): checksum for version, checksum in inputs.dump_pin.source_migrations},
                "LOCAL_UPGRADE_RESTORED_PREFIX_CHANGED",
            )
            owner = connection.execute(
                "SELECT pg_get_userbyid(datdba)=current_user AS valid FROM pg_database WHERE datname=current_database()"
            ).fetchone()
            require(owner["valid"], "LOCAL_UPGRADE_DATABASE_OWNER_CHANGED")
            # This is the existing Migrator's path; migration0007 freezes this trigger configuration.
            connection.execute("SET LOCAL search_path=mingjing_core")
            forward = sorted(set(expected) - set(actual))
            for version in forward:
                connection.execute(sources[version])
                connection.execute(
                    "INSERT INTO mingjing_core.schema_migrations(version,checksum) VALUES(%s,%s)",
                    (version, expected[version]),
                )
            validate_history(_history(connection), expected, complete=True)
    except EvidenceError:
        raise RestoreRejected("LOCAL_UPGRADE_HISTORY_REJECTED") from None
    except psycopg.Error:
        raise RestoreRejected("LOCAL_UPGRADE_CORE_TRANSACTION_FAILED") from None
    return forward


def _checkpoint(connection: Any) -> int:
    try:
        # PostgresSaver's concurrent index migrations require a separate autocommit stage.
        connection.execute("SET search_path=public")
        saver = PostgresSaver(connection)
        saver.setup()
        versions = connection.execute("SELECT v FROM public.checkpoint_migrations ORDER BY v").fetchall()
        require(
            [row["v"] for row in versions] == list(range(len(saver.MIGRATIONS))),
            "LOCAL_UPGRADE_CHECKPOINT_HISTORY_REJECTED",
        )
    except psycopg.Error:
        raise RestoreRejected("LOCAL_UPGRADE_CHECKPOINT_FAILED") from None
    return len(versions)


def _empty_quota(connection: Any) -> None:
    checks = [sql.SQL("EXISTS(SELECT 1 FROM {})").format(sql.Identifier(*name.split("."))) for name in QUOTA]
    row = connection.execute(sql.SQL("SELECT {} AS occupied").format(sql.SQL(" OR ").join(checks))).fetchone()
    require(not row["occupied"], "LOCAL_UPGRADE_CENTRAL_TABLE_NOT_EMPTY")


def _grant(connection: Any, writer: str) -> None:
    try:
        with connection.transaction():
            connection.execute("SET LOCAL search_path=pg_catalog")
            grant_runtime_tables(connection, writer)
            grant_checkpoints(connection, writer)
    except (psycopg.Error, RuntimeError):
        raise RestoreRejected("LOCAL_UPGRADE_GRANTS_FAILED") from None


def _upgrade_new_target(inputs: LocalInputs, dsns: dict[str, str], creator: Any) -> dict[str, Any]:
    _require_creator(inputs, dsns, creator)
    sources = _sources(inputs)
    with psycopg.connect(dsns["owner"], autocommit=True, row_factory=dict_row) as connection:
        connection.execute("SET search_path=pg_catalog")
        server_identity(connection, conninfo_to_dict(dsns["owner"]))
        forward = _migrate(connection, inputs, sources)
        checkpoint_count = _checkpoint(connection)
        connection.execute("SET search_path=pg_catalog")
        _empty_quota(connection)
        _grant(connection, inputs.contract.database + "_writer")
        _empty_quota(connection)
    try:
        acl = verify_database_acl(
            inputs.contract,
            inputs.release,
            environment={"FIRST_RELEASE_" + role.upper() + "_DSN": dsns[role] for role in ("owner", "writer")},
        )
    except RestoreRejected:
        raise RestoreRejected("LOCAL_UPGRADE_ACL_REJECTED") from None
    return {
        "schema": "first-release-local-upgrade-v1",
        "local_upgrade_completed": True,
        "forward_migrations": forward,
        "upgraded_migrations": dict(inputs.release.migrations),
        "checkpoint_migrations_checked": checkpoint_count,
        "central_ledger_empty": True,
        "central_binding_verified": False,
        "central_provisioned": False,
        "runtime_acl_verified": True,
        "acl": acl,
        "database_connections": 7,
    }

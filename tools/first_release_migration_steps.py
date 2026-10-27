"""Neutral pinned forward SQL; callers must establish fresh-target or strict-source authority."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.foundation import validate_history
from mingjing_core.repositories.permissions import grant_runtime_tables
from tools.first_release_contracts import ReleasePin, RestoreRejected, ordinary, require
from tools.first_release_source import MIGRATION_DIR, verify_source


@dataclass(frozen=True)
class MigrationBundle:
    release: ReleasePin
    root: Path
    statements: tuple[tuple[int, str], ...]

    def verify(self) -> None:
        verify_source(self.root, self.release)
        require(
            type(self.statements) is tuple
            and len(self.statements) == 8
            and all(type(item) is tuple and len(item) == 2 for item in self.statements)
            and tuple(version for version, _ in self.statements) == tuple(range(1, 9)),
            "FORWARD_EXACT_SQL_1_8",
        )
        expected = dict(self.release.migrations)
        for version, statement in self.statements:
            require(
                type(version) is int
                and isinstance(statement, str)
                and hashlib.sha256(statement.encode()).hexdigest() == expected[str(version)],
                "FORWARD_REVIEWED_SQL_CHANGED",
            )


def load_bundle(release: ReleasePin, root: Path) -> MigrationBundle:
    verify_source(root, release)
    statements = []
    for path in sorted((root / MIGRATION_DIR).glob("[0-9][0-9][0-9][0-9]_*.sql")):
        ordinary(path)
        statements.append((int(path.name[:4]), path.read_text(encoding="utf-8").replace("\r\n", "\n")))
    bundle = MigrationBundle(release, root, tuple(statements))
    bundle.verify()
    return bundle


def history(connection: Any) -> dict[int, str]:
    return {
        row["version"]: row["checksum"]
        for row in connection.execute("SELECT version,checksum FROM mingjing_core.schema_migrations")
    }


def forward_core(
    connection: Any,
    bundle: MigrationBundle,
    prefix: tuple[tuple[str, str], ...],
    *,
    prepare_locked_source: Callable[[Any], None] | None = None,
) -> list[int]:
    """Preserve one Core transaction; the source callback locks before any data snapshot."""
    bundle.verify()
    expected = {int(version): checksum for version, checksum in bundle.release.migrations}
    require(
        type(prefix) is tuple
        and 1 <= len(prefix) <= 7
        and all(type(item) is tuple and len(item) == 2 for item in prefix)
        and tuple(version for version, _ in prefix) == tuple(str(number) for number in range(1, len(prefix) + 1)),
        "FORWARD_ORIGINAL_PREFIX_REQUIRED",
    )
    original = {int(version): checksum for version, checksum in prefix}
    validate_history(original, expected, complete=False)
    try:
        with connection.transaction():
            connection.execute("SET LOCAL search_path=pg_catalog")
            if prepare_locked_source is not None:
                connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
                prepare_locked_source(connection)
                locked = connection.execute(
                    "SELECT pg_try_advisory_xact_lock(hashtextextended('mingjing_core:schema',0)) AS locked"
                ).fetchone()["locked"]
                require(locked, "FORWARD_SOURCE_SCHEMA_BUSY")
            else:
                connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('mingjing_core:schema',0))")
            actual = history(connection)
            validate_history(actual, expected, complete=False)
            require(actual == original, "FORWARD_ORIGINAL_PREFIX_CHANGED")
            require(
                connection.execute(
                    "SELECT pg_get_userbyid(datdba)=current_user AS owned "
                    "FROM pg_database WHERE datname=current_database()"
                ).fetchone()["owned"],
                "FORWARD_DATABASE_OWNER_CHANGED",
            )
            connection.execute("SET LOCAL search_path=mingjing_core")
            forward = sorted(set(expected) - set(actual))
            for version in forward:
                connection.execute(dict(bundle.statements)[version])
                connection.execute(
                    "INSERT INTO mingjing_core.schema_migrations(version,checksum) VALUES(%s,%s)",
                    (version, expected[version]),
                )
            validate_history(history(connection), expected, complete=True)
    except EvidenceError:
        raise RestoreRejected("FORWARD_HISTORY_REJECTED") from None
    except psycopg.Error:
        raise RestoreRejected("FORWARD_CORE_TRANSACTION_FAILED") from None
    return forward


def grant_checkpoint_tables(connection: Any, writer: str) -> None:
    role, database = sql.Identifier(writer), sql.Identifier(writer.removesuffix("_writer"))
    connection.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(database))
    connection.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(database, role))
    connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role))
    connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
    for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"):
        require(
            connection.execute("SELECT to_regclass(%s) AS name", ("public." + name,)).fetchone()["name"],
            "FORWARD_CHECKPOINT_TABLE_MISSING",
        )
        rights = "SELECT" if name == "checkpoint_migrations" else "SELECT,INSERT,UPDATE,DELETE"
        connection.execute(sql.SQL("GRANT {} ON public.{} TO {}").format(sql.SQL(rights), sql.Identifier(name), role))
    for table in ("public.checkpoint_migrations", "mingjing_core.schema_migrations"):
        connection.execute(
            sql.SQL("REVOKE INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER ON {} FROM {}").format(
                sql.Identifier(*table.split(".")), role
            )
        )


def grant_new_runtime(connection: Any, writer: str) -> None:
    """Reapply final grants only after the caller rejected any deficient or excessive source ACL."""
    with connection.transaction():
        connection.execute("SET LOCAL search_path=pg_catalog")
        grant_runtime_tables(connection, writer)
        grant_checkpoint_tables(connection, writer)

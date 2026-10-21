"""Pinned-candidate migration/replay, invoked only in a fresh isolated process."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from psycopg import sql

from tools.b1_restore_proof_contracts import ProofRequest, verify_monotone
from tools.b1_restore_proof_pg import checksums, identity, quiescent, state_hash
from tools.b1_restore_replay_contracts import require
from tools.core_incremental_contracts import MIGRATIONS


def modules(request: ProofRequest) -> tuple[Any, Any, Any]:
    repository = importlib.import_module("mingjing_core.repositories.postgres")
    deployment = importlib.import_module("tools.deploy_core")
    permissions = importlib.import_module("mingjing_core.repositories.permissions")
    for module in (repository, deployment, permissions):
        require(
            Path(module.__file__).resolve().is_relative_to(request.candidate_source.resolve()), "WRONG_CANDIDATE_IMPORT"
        )
    return repository, deployment, permissions


def migrate(request: ProofRequest) -> dict[str, Any]:
    repository, _, permissions = modules(request)
    repo = repository.PostgresRepository(request.dsn("owner"), initialize=False, max_size=1)
    try:
        with repo.transaction() as conn:
            identity(conn, request, "owner")
            quiescent(conn)
            require(
                checksums(conn) == {str(key): MIGRATIONS[str(key)] for key in range(1, 5)}, "RESTORED_SCHEMA4_REQUIRED"
            )
        repo.initialize()
        repo.verify_schema()
        with repo.transaction() as conn:
            permissions.grant_runtime_tables(conn, request.database + "_writer")
            grant_checkpoints(conn, request.database + "_writer")
            actual = checksums(conn)
            require(actual == MIGRATIONS, "PINNED_SCHEMA7_REQUIRED")
        return {"checksums": actual, "forward_migrations": [5, 6, 7]}
    finally:
        repo.close()


def grant_checkpoints(conn: Any, writer: str) -> None:
    role = sql.Identifier(writer)
    database = sql.Identifier(writer.removesuffix("_writer"))
    conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(database))
    conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(database, role))
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role))
    conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"):
        require(
            conn.execute("SELECT to_regclass(%s) AS name", ("public." + table,)).fetchone()["name"],
            "CHECKPOINT_TABLE_MISSING",
        )
        rights = "SELECT" if table == "checkpoint_migrations" else "SELECT,INSERT,UPDATE,DELETE"
        conn.execute(sql.SQL("GRANT {} ON public.{} TO {}").format(sql.SQL(rights), sql.Identifier(table), role))
    for table in ("public.checkpoint_migrations", "mingjing_core.schema_migrations"):
        namespace, name = table.split(".")
        conn.execute(
            sql.SQL("REVOKE INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER ON {}.{} FROM {}").format(
                sql.Identifier(namespace), sql.Identifier(name), role
            )
        )


def preflight(repo: Any, conn: Any, request: ProofRequest, document: dict[str, Any]) -> None:
    identity(conn, request, "owner")
    quiescent(conn)
    require(checksums(conn) == MIGRATIONS, "PINNED_SCHEMA7_REQUIRED")
    owners = {row["id"] for row in conn.execute("SELECT id FROM mingjing_core.core_owners")}
    require(owners == {row["owner_user_id"] for row in document["owners"]}, "COMPLETE_OWNER_LEDGER_REQUIRED")
    counts = conn.execute(
        "SELECT count(*) FILTER(WHERE status IN ('queued','running')) AS active,"
        "count(*) FILTER(WHERE lease_until>now()) AS leases FROM mingjing_core.core_runs"
    ).fetchone()
    require(counts == {"active": 0, "leases": 0}, "RESTORE_NOT_QUIESCENT")
    require(
        conn.execute(
            "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS ok", (request.database + ":b1-restore-proof",)
        ).fetchone()["ok"],
        "RESTORE_PROOF_LOCKED",
    )


def verify_erased(repo: Any, conn: Any, document: dict[str, Any]) -> dict[str, int]:
    whole, draws, checkpoints = 0, 0, 0
    for ledger in document["owners"]:
        for row in ledger["revocations"]:
            if row["kind"] in {"source_span", "legacy_memory"}:
                continue
            existing = conn.execute(
                "SELECT status,data FROM mingjing_core.core_entities WHERE owner=%s AND kind=%s AND id=%s",
                (ledger["owner_user_id"], row["kind"], row["entity_id"]),
            ).fetchone()
            require(
                not existing or existing["status"] == "deleted" and existing["data"] == {}, "WITHDRAWN_ENTITY_SURVIVED"
            )
            whole += 1
    for row in document["deleted_draws"]:
        exists = conn.execute(
            "SELECT 1 FROM mingjing_core.tarot_draws WHERE owner=%s AND id=%s", (row["owner"], row["draw_id"])
        ).fetchone()
        require(exists is None, "DELETED_DRAW_SURVIVED")
        draws += 1
    runs = conn.execute("SELECT id,retry_epoch FROM mingjing_core.core_runs WHERE status='revoked'").fetchall()
    for run in runs:
        for epoch in range(run["retry_epoch"] + 1):
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                found = conn.execute(
                    sql.SQL("SELECT 1 FROM public.{} WHERE thread_id=%s LIMIT 1").format(sql.Identifier(table)),
                    (run["id"] + ":e" + str(epoch),),
                ).fetchone()
                require(found is None, "REVOKED_CHECKPOINT_SURVIVED")
                checkpoints += 1
    return {
        "whole_revocations_checked": whole,
        "deleted_draws_checked": draws,
        "checkpoint_ranges_checked": checkpoints,
    }


def replay(request: ProofRequest, document: dict[str, Any]) -> dict[str, Any]:
    repository, deployment, _ = modules(request)
    repo = repository.PostgresRepository(request.dsn("owner"), initialize=False, max_size=1)
    try:
        repo.verify_schema()
        with repo.transaction() as conn:
            preflight(repo, conn, request, document)
            before = state_hash(conn)
        counts = deployment.apply_withdrawals(repo, document)
        exported = deployment.export_withdrawals(repo)
        verify_monotone(document, exported)
        with repo.transaction() as conn:
            preflight(repo, conn, request, document)
            verified = verify_erased(repo, conn, document)
            after = state_hash(conn)
        return {
            "state_before_sha256": before,
            "state_after_sha256": after,
            "changed": before != after,
            "counts": counts,
            **verified,
        }
    finally:
        repo.close()

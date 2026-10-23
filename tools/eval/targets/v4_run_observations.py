"""Evaluator projections of native run rows and independently stored inputs."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.repositories.postgres import PostgresRepository


def native_run_rows(repo: PostgresRepository, owner: str) -> list[dict[str, Any]]:
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL("SELECT id,status,retry_epoch FROM {} WHERE owner=%s ORDER BY id").format(
                repo.table("core_runs")
            ),
            (owner,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "kind": "run",
            "status": row["status"],
            "data": dict(row),
            "source_store": "core_runs",
        }
        for row in rows
    ]


def native_run_meta(repo: PostgresRepository, owner: str, run: dict[str, Any]) -> dict[str, Any]:
    if not run:
        return {}
    identifiers = run.get("request", {}).get("source_message_ids", [])
    sources = [repo.get(owner, "message", ident) for ident in identifiers]
    return {
        "status": "completed" if run["status"] == "succeeded" else run["status"],
        "native_status": run["status"],
        "input_message_ids": [row["source_id"] for row in sources],
        "source_store": "core_runs + native source messages",
    }

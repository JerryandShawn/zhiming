"""Read actual native privacy stores; keep raw tombstones visible, without legacy status rewriting."""

from __future__ import annotations

from typing import Any

from psycopg import sql


def runtime_rows(seed: Any) -> list[dict[str, Any]]:
    target = seed.target
    if not seed.runtime_ids:
        return []
    with target.repo.transaction(target.owner) as connection:
        events = connection.execute(
            sql.SQL(
                "SELECT run_id,seq,kind FROM {} WHERE owner=%s AND run_id=ANY(%s) AND payload!='{{}}'::jsonb"
            ).format(target.repo.table("core_run_events")),
            (target.owner, seed.runtime_ids),
        ).fetchall()
        steps = connection.execute(
            sql.SQL(
                "SELECT run_id,epoch,seq,kind,status FROM {} WHERE owner=%s AND run_id=ANY(%s) AND output IS NOT NULL"
            ).format(target.repo.table("core_run_steps")),
            (target.owner, seed.runtime_ids),
        ).fetchall()
    return [
        {
            "kind": kind,
            "id": f"{row['run_id']}:{row['seq']}",
            "status": "active",
            "data": dict(row),
            "source_store": table,
        }
        for kind, table, rows in [
            ("run_event", "core_run_events.payload", events),
            ("run_step", "core_run_steps.output", steps),
        ]
        for row in rows
    ]


def privacy_rows(seed: Any) -> list[dict[str, Any]]:
    target = seed.target
    if not seed.source_ids:
        return []
    with target.repo.transaction(target.owner) as connection:
        embeddings = connection.execute(
            sql.SQL("SELECT kind,entity_id,chunk,model FROM {} WHERE owner=%s").format(
                target.repo.table("core_embeddings")
            ),
            (target.owner,),
        ).fetchall()
    profiles = [r for r in target.repo.list(target.owner, "profile_doc") if r["id"] in seed.ids.values()]
    search = seed.search()
    return (
        runtime_rows(seed)
        + [
            {
                "kind": "embedding",
                "id": r["entity_id"],
                "status": "active",
                "data": dict(r),
                "source_store": "core_embeddings",
            }
            for r in embeddings
        ]
        + [
            {
                "kind": "profile_item",
                "id": r["id"],
                "status": r["status"],
                "data": r,
                "source_store": "core_entities.profile_doc",
            }
            for r in profiles
        ]
        + [
            {
                "kind": "search_hit",
                "id": r["id"],
                "status": r["status"],
                "data": {"entity_id": r["id"]},
                "source_store": "actual repo.search",
            }
            for r in search
        ]
    )


def native_counts(seed: Any) -> dict[str, int]:
    rows = privacy_rows(seed)
    return {
        kind: sum(r["kind"] == kind for r in rows)
        for kind in ["embedding", "profile_item", "search_hit", "run_event", "run_step"]
    }

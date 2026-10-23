"""Conceptual privacy views backed by native rows, cleared bodies and tombstones."""

from __future__ import annotations

from typing import Any

from psycopg import sql


def erased(repo: Any, owner: str, kind: str, ident: str) -> bool:
    with repo.transaction(owner) as connection:
        row = connection.execute(
            sql.SQL("SELECT status,data FROM {} WHERE owner=%s AND kind=%s AND id=%s").format(
                repo.table("core_entities")
            ),
            (owner, kind, ident),
        ).fetchone()
    return bool(row and row["status"] == "deleted" and row["data"] == {} and repo.is_revoked(owner, kind, ident))


def layer_rows(repo: Any, owner: str, layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for layer in layers:
        kind = layer["kind"]
        if kind in {"embedding", "search_hit", "run_event", "run_step"}:
            with repo.transaction(owner) as connection:
                if kind == "embedding":
                    found = connection.execute(
                        sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND kind=%s AND entity_id=%s").format(
                            repo.table("core_embeddings")
                        ),
                        (owner, layer["native_kind"], layer["native_id"]),
                    ).fetchone()
                    store = "core_embeddings"
                elif kind == "search_hit":
                    found = connection.execute(
                        sql.SQL(
                            "SELECT 1 FROM {} WHERE owner=%s AND kind=%s AND id=%s "
                            "AND status='active' AND search!=''::tsvector"
                        ).format(repo.table("core_entities")),
                        (owner, layer["native_kind"], layer["native_id"]),
                    ).fetchone()
                    store = "core_entities.search"
                else:
                    table, predicate = (
                        ("core_run_events", "payload!='{}'::jsonb")
                        if kind == "run_event"
                        else ("core_run_steps", "output IS NOT NULL")
                    )
                    found = connection.execute(
                        sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND run_id=%s AND {}").format(
                            repo.table(table), sql.SQL(predicate)
                        ),
                        (owner, layer["native_run"]),
                    ).fetchone()
                    store = table
            if found:
                result.append(
                    {
                        "kind": kind,
                        "id": layer["id"],
                        "status": "active",
                        "data": {"source_store": store, "native_id": layer.get("native_id", layer.get("native_run"))},
                    }
                )
        elif kind == "profile_item":
            row = repo.get(owner, layer["native_kind"], layer["native_id"], include_deleted=True)
            if not erased(repo, owner, layer["native_kind"], layer["native_id"]):
                result.append(
                    {
                        "kind": kind,
                        "id": layer["id"],
                        "status": row["status"],
                        "data": dict(row, source_store="core_entities.profile_doc"),
                    }
                )
    return result


def privacy_entities(
    repo: Any,
    owner: str,
    layers: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        kind, ident = row["kind"], row["id"]
        if kind == "message" and ident in (aliases or {}):
            row = dict(row, id=aliases[ident], native_id=ident, source_store="core_entities.message")
        if kind == "fact" and erased(repo, owner, kind, ident):
            spans = [
                rev["metadata"]
                for rev in repo.revocations(owner)
                if rev["kind"] == "source_span" and ident in rev["metadata"].get("fact_ids", [])
            ]
            if spans and not any(repo.is_revoked(owner, "message", span["message_id"]) for span in spans):
                result.append(
                    dict(
                        row,
                        status="retired",
                        native_status="deleted",
                        data={"source_store": "core_entities + core_revocations", "native_status": "deleted"},
                    )
                )
        elif kind in {"note", "episode", "thread_summary", "profile_doc", "proposal"} and erased(
            repo, owner, kind, ident
        ):
            continue
        elif kind == "followup" and erased(repo, owner, kind, ident):
            layer = next((layer for layer in layers if layer["kind"] == kind and layer["native_id"] == ident), None)
            if layer and layer.get("fact_id") and repo.is_revoked(owner, "fact", layer["fact_id"]):
                result.append(
                    dict(
                        row,
                        status="cancelled",
                        native_status="deleted",
                        data={"source_store": "core_entities + core_revocations", "native_status": "deleted"},
                    )
                )
            else:
                result.append(row)
        else:
            result.append(row)
    return result + layer_rows(repo, owner, layers)


def initial_layers(repo: Any, owner: str, layers: list[dict[str, Any]]) -> dict[str, int]:
    counts = {}
    native = layer_rows(repo, owner, layers)
    for layer in layers:
        if layer["kind"] in {"embedding", "search_hit", "run_event", "run_step", "profile_item"}:
            present = any(row["id"] == layer["id"] and row["kind"] == layer["kind"] for row in native)
        else:
            row = repo.get(owner, layer["native_kind"], layer["native_id"])
            expected_status = "pending" if layer.get("actual_p3_pending") is True else "active"
            present = row["status"] == expected_status and bool(row.get("source_refs"))
        if not present:
            raise ValueError("Declared privacy layer absent before withdrawal: " + layer["id"])
        counts[layer["kind"]] = counts.get(layer["kind"], 0) + 1
    return counts

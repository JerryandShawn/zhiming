"""Native historical search/vector/runtime rows for offline privacy fixtures."""

from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.repositories.postgres import fingerprint


def historical_run(seeder: Any, sources: list[str], ident: str) -> str:
    repo, owner = seeder.service.repo, seeder.owner
    run = repo.queue_run(
        owner, "seed-history:" + ident, {"source_message_id": sources[0], "message": "synthetic historical run"}
    )
    versions = {"message:" + value: repo.get(owner, "message", value)["revision"] for value in sources}
    with repo.transaction(owner) as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET status='succeeded',state_version=%s WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            (Jsonb(versions), owner, run["id"]),
        )
    return run["id"]


def seed_native_layer(seeder: Any, record: dict[str, Any], refs: list[dict[str, Any]]) -> None:
    repo, owner = seeder.service.repo, seeder.owner
    kind, fact_id, sources = record["kind"], record["fact_id"], record["sources"]
    if kind == "search_hit":
        if not fact_id:
            raise ValueError("Search fixture needs a real fact")
        record.update(native_kind="fact", native_id=fact_id)
        with repo.transaction(owner) as connection:
            active = connection.execute(
                sql.SQL(
                    "SELECT search!=''::tsvector AS indexed FROM {} "
                    "WHERE owner=%s AND kind='fact' AND id=%s AND status='active'"
                ).format(repo.table("core_entities")),
                (owner, fact_id),
            ).fetchone()
        if not active or not active["indexed"]:
            raise ValueError("Declared search hit was not actually indexed")
    elif kind == "embedding":
        native_kind, native_id = ("fact", fact_id) if fact_id else ("message", sources[0])
        record.update(native_kind=native_kind, native_id=native_id)
        with repo.transaction(owner) as connection:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}(owner,kind,entity_id,chunk,model,vec,content_fp) "
                    "VALUES(%s,%s,%s,0,'synthetic-fixture-2d',%s,%s)"
                ).format(repo.table("core_embeddings")),
                (owner, native_kind, native_id, [1.0, 0.0], fingerprint(refs)),
            )
    else:
        record["native_run"] = historical_run(seeder, sources, record["id"])
        seed_runtime_row(repo, owner, record, refs)


def seed_runtime_row(repo: Any, owner: str, record: dict[str, Any], refs: list[dict[str, Any]]) -> None:
    with repo.transaction(owner) as connection:
        if record["kind"] == "run_event":
            connection.execute(
                sql.SQL("INSERT INTO {}(owner,run_id,seq,kind,payload) VALUES(%s,%s,1,'status',%s)").format(
                    repo.table("core_run_events")
                ),
                (
                    owner,
                    record["native_run"],
                    Jsonb({"text": "synthetic prior derived event", "source_ids": record["sources"]}),
                ),
            )
        else:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}(owner,run_id,epoch,seq,kind,name,status,input_fp,output) "
                    "VALUES(%s,%s,0,1,'model','seed','completed',%s,%s)"
                ).format(repo.table("core_run_steps")),
                (
                    owner,
                    record["native_run"],
                    fingerprint(refs),
                    Jsonb({"text": "synthetic prior derived step", "source_ids": record["sources"]}),
                ),
            )

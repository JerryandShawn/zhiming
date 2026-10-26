"""Withdraw only transient comparison steps, including pre-finalization outputs."""

from psycopg import sql

from .privacy_closure import linked_ids


def transient_rows(repo, owner, facts, sources, runs):
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND kind='runtime_step' AND status!='deleted' "
                "AND data @> '{{\"ephemeral_synastry\":true}}'"
            ).format(repo.table("core_entities")),
            (owner,),
        ).fetchall()
    result = [dict(repo._decode(row), entity_kind="runtime_step") for row in rows]
    for row in result:
        linked, used = linked_ids(row)
        if sources.intersection(linked) or facts.intersection(used):
            runs.add(row["run_id"])
    return result

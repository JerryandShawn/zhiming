"""Only versioned Case effect records join the generic withdrawal closure."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.domain.case_effects import SCHEMA, STAGE


def case_effect_rows(repo: Any, owner: str) -> list[dict[str, Any]]:
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND kind='runtime_step' AND status!='deleted' "
                "AND data->>'schema'=%s AND data->>'stage'=%s"
            ).format(repo.table("core_entities")),
            (owner, SCHEMA, STAGE),
        ).fetchall()
    result = []
    for raw in rows:
        row = repo._decode(raw)
        # Case deletion is a seed entity in the existing closure; do not persist
        # these extra identifier links as user-source message lineage.
        links = set(row.get("source_ids", [])) | set(row.get("case_ids", []))
        if row.get("case_id"):
            links.add(row["case_id"])
        result.append(dict(row, entity_kind="runtime_step", source_ids=sorted(links)))
    return result

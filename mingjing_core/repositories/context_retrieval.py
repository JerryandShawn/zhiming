"""Bounded OR candidates for natural time queries; original AND search stays unchanged."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from psycopg import sql

from mingjing_core.memory.projections import project_search
from mingjing_core.memory.tokenize import tokenize

if TYPE_CHECKING:
    from mingjing_core.repositories.postgres import PostgresRepository


def time_query_candidates(
    repo: PostgresRepository, owner: str, subject: str, tokens: list[str]
) -> list[dict[str, Any]]:
    if not tokens or len(tokens) > 32:
        raise ValueError("时间检索需要有限的关键词")
    expression = sql.SQL(" || ").join(sql.SQL("plainto_tsquery('simple',%s)") for _ in tokens)
    query = sql.SQL(
        "SELECT *,ts_rank(search,({terms})) AS rank FROM {table} "
        "WHERE owner=%s AND subject=%s AND status='active' AND kind IN ('message','fact') "
        "AND search @@ ({terms}) ORDER BY rank DESC,created_at DESC,id DESC LIMIT 100"
    ).format(terms=expression, table=repo.table("core_entities"))
    with repo.transaction(owner) as connection:
        repo.assert_scope(owner, subject)
        records = connection.execute(query, (*tokens, owner, subject, *tokens)).fetchall()
    decoded = [dict(repo._decode(row), _retrieval_kind=row["kind"], search_rank=row["rank"]) for row in records]
    # The old projection owns withdrawal/private filtering. Recheck OR membership
    # after redaction so removed words cannot keep a candidate in the result.
    projected = project_search(repo, owner, decoded, ())
    wanted = set(tokens)
    return [
        row
        for row in projected
        if wanted.intersection(tokenize("\n".join(str(row.get(key, "")) for key in ("content", "text", "summary"))))
    ]

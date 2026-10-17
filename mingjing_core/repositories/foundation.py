"""Forward migration checks and owner-scoped foundation queries."""

from __future__ import annotations

import hashlib
from pathlib import Path

from psycopg import sql

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.memory.projections import project_search


def migration_manifest() -> dict[int, str]:
    paths = sorted(Path(__file__).with_name("migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    result = {
        int(path.name[:4]): hashlib.sha256(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest()
        for path in paths
    }
    if not result or sorted(result) != list(range(1, max(result) + 1)) or len(result) != len(paths):
        raise EvidenceError("Versioned migration files are missing or duplicated")
    return result


def validate_history(actual: dict, expected: dict, *, complete: bool) -> None:
    if set(actual) - set(expected):
        raise EvidenceError("Database schema is newer than this release")
    if actual and sorted(actual) != list(range(1, max(actual) + 1)):
        raise EvidenceError("Database migration history has a gap")
    if any(actual[version] != expected[version] for version in actual):
        raise EvidenceError("Migration checksum mismatch or unverified historical baseline")
    if complete and set(actual) != set(expected):
        raise EvidenceError("Pending known migrations require the separate migration role")


def list_entities(
    repo, owner, kind, *, subject=None, case_ids=None, include_deleted=False, limit=10000, order="asc", before=None
):
    repo._kind(kind)
    if order not in ("asc", "desc"):
        raise ValueError("Entity order must be asc or desc")
    with repo.transaction(owner) as connection:
        repo.assert_scope(owner, subject or "self")
        query = sql.SQL("SELECT * FROM {} WHERE owner=%s AND kind=%s").format(repo.table("core_entities"))
        args = [owner, kind]
        if subject is not None:
            query += sql.SQL(" AND subject=%s")
            args.append(subject)
        if case_ids is not None:
            query += sql.SQL(" AND (case_id IS NULL OR case_id=ANY(%s))")
            args.append(case_ids)
        if not include_deleted:
            query += sql.SQL(" AND status!='deleted'")
        if before is not None:
            if isinstance(before, (tuple, list)) and len(before) == 2:
                query += sql.SQL(" AND (created_at,id)<(%s::timestamptz,%s)")
                args.extend(before)
            else:
                query += sql.SQL(" AND created_at<%s::timestamptz")
                args.append(before)
        query += sql.SQL(" ORDER BY created_at {},id {} LIMIT %s").format(sql.SQL(order), sql.SQL(order))
        args.append(max(1, min(int(limit), 100000)))
        return [repo._decode(row) for row in connection.execute(query, args).fetchall()]


def thread_history(repo, owner, subject, thread_id, case_ids, limit):
    with repo.transaction(owner) as connection:
        repo.assert_scope(owner, subject)
        query = sql.SQL("""SELECT * FROM {} WHERE owner=%s AND subject=%s AND kind='message' AND status='active'
            AND data->>'thread_id'=%s AND (coalesce(data->'case_ids','[]')='[]'::jsonb OR data->'case_ids' ?| %s)
            ORDER BY (data->>'at_ms')::bigint DESC,created_at DESC,id DESC LIMIT %s""").format(
            repo.table("core_entities")
        )
        return [
            repo._decode(row)
            for row in connection.execute(query, (owner, subject, thread_id, list(case_ids or []), limit)).fetchall()
        ]


def search(repo, owner, subject, query_tokens, kinds, limit, since=None, until=None):
    if isinstance(query_tokens, str) or not query_tokens or not all(isinstance(token, str) for token in query_tokens):
        raise ValueError("Search needs a nonempty token list")
    for kind in kinds:
        repo._kind(kind)
    with repo.transaction(owner) as connection:
        repo.assert_scope(owner, subject)
        query = sql.SQL("""SELECT *,ts_rank(search,plainto_tsquery('simple',%s)) AS rank FROM {}
            WHERE owner=%s AND subject=%s AND status='active' AND kind=ANY(%s)
            AND search @@ plainto_tsquery('simple',%s)""").format(repo.table("core_entities"))
        text = " ".join(query_tokens)
        args = [text, owner, subject, list(kinds), text]
        for boundary, operator in ((since, ">="), (until, "<=")):
            if boundary is not None:
                query += sql.SQL(" AND created_at {} %s::timestamptz").format(sql.SQL(operator))
                args.append(boundary)
        query += sql.SQL(" ORDER BY rank DESC,created_at DESC,id DESC LIMIT %s")
        args.append(max(1, min(int(limit), 100)))
        rows = [dict(repo._decode(row), search_rank=row["rank"]) for row in connection.execute(query, args).fetchall()]
        return project_search(repo, owner, rows, query_tokens)

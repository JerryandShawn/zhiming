"""Withdrawn original ranges stay absent from both search tokens and results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg import sql

from .tokenize import searchable_data, tokenize

if TYPE_CHECKING:
    from collections.abc import Collection

    # Projection values come from heterogeneous entity JSON and revocation rows.
    from typing import Any

    from mingjing_core.repositories.postgres import PostgresRepository


def redact_ranges(text: str, spans: list[dict]) -> str:
    intervals = []
    for span in spans:
        start, end = span.get("start"), span.get("end")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            return "〔已删除的内容〕"
        intervals.append((start, end))
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        text = text[:start] + "[该资料已撤销]" + text[end:]
    return text


def owner_spans(repo: PostgresRepository, owner: str) -> tuple[dict[str | None, list[dict[str, Any]]], set[str]]:
    spans, deleted = {}, set()
    for row in repo.revocations(owner):
        if row["kind"] == "source_span":
            span = row["metadata"]
            spans.setdefault(span.get("message_id"), []).append(span)
        elif row["kind"] == "message":
            deleted.add(row["entity_id"])
    return spans, deleted


def tokenized_payload(
    repo: PostgresRepository, owner: str, kind: str, ident: str, payload: dict[str, Any]
) -> dict[str, Any]:
    if kind != "message" or not payload:
        return searchable_data(kind, payload)
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT metadata FROM {} WHERE owner=%s AND kind='source_span' AND metadata->>'message_id'=%s"
            ).format(repo.table("core_revocations")),
            (owner, ident),
        ).fetchall()
    projected = dict(payload, content=redact_ranges(payload.get("content", ""), [row["metadata"] for row in rows]))
    return dict(payload, search_tokens=searchable_data(kind, projected)["search_tokens"])


def project_search(
    repo: PostgresRepository, owner: str, rows: list[dict[str, Any]], query_tokens: Collection[str]
) -> list[dict[str, Any]]:
    spans, deleted = owner_spans(repo, owner)
    result = []
    for row in rows:
        if row.get("role") is not None:
            if row["id"] in deleted:
                continue
            content = redact_ranges(row.get("content", ""), spans.get(row["id"], []))
            if not set(token.lower() for token in query_tokens) <= set(tokenize(content)):
                continue
            row = dict(row, content=content)
        result.append(row)
    return result

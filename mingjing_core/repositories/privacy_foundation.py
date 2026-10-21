"""Deterministic withdrawal of the new derived storage layers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.projections import owner_spans, redact_ranges
from mingjing_core.memory.tokenize import searchable_data

from .privacy_case_effects import case_effect_rows
from .privacy_cases import redact_case_fields
from .privacy_closure import closure_rows, partial_sources, propagate

if TYPE_CHECKING:
    from collections.abc import Collection

    # Entity and revocation metadata carry heterogeneous JSON values.
    from typing import Any

    from mingjing_core.repositories.postgres import PostgresRepository

DERIVED_KINDS = ("thread_summary", "note", "profile_doc", "knowledge_gap", "followup", "reminder", "proposal")


def redact_assistant(repo: PostgresRepository, owner: str, message: dict[str, Any]) -> dict[str, Any]:
    result = repo.update(
        owner,
        "message",
        message["id"],
        {"content": "〔已删除的内容〕", "redacted": True, "source_refs": []},
        expected_revision=message["revision"],
    )
    with repo.transaction(owner) as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner=%s AND kind='message' AND entity_id=%s").format(
                repo.table("core_embeddings")
            ),
            (owner, message["id"]),
        )
    return result


def refresh_source_indexes(repo: PostgresRepository, owner: str, spans: dict[str | None, list[dict[str, Any]]]) -> None:
    for ident, ranges in spans.items():
        try:
            message = repo.get(owner, "message", ident, include_deleted=True)
        except (ValueError, KeyError, ScopeError, EvidenceError):
            continue
        if message["status"] == "deleted":
            continue
        projected = dict(message, content=redact_ranges(message.get("content", ""), ranges))
        tokens = searchable_data("message", projected)["search_tokens"]
        with repo.transaction(owner) as connection:
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET data=jsonb_set(data,'{{search_tokens}}',%s) WHERE owner=%s "
                    "AND kind='message' AND id=%s"
                ).format(repo.table("core_entities")),
                (Jsonb(tokens), owner, ident),
            )


def invalidate_foundation(
    repo: PostgresRepository,
    owner: str,
    fact_ids: Collection[str],
    source_ids: Collection[str],
    run_ids: Collection[str] = (),
    *,
    span_source_ids: Collection[str] = (),
    recomputable: bool = False,
    seed_entities: Collection[tuple[str, str]] = (),
) -> tuple[list[str], list[str], set[str]]:
    facts, sources, runs = set(fact_ids), set(source_ids), set(run_ids)
    partial = partial_sources(repo, owner, facts, span_source_ids)
    sources.update(partial | {ident for _, ident in seed_entities})
    entities, run_rows = closure_rows(repo, owner, (*DERIVED_KINDS, "message", "episode", "interpretive_claim"))
    entities.extend(case_effect_rows(repo, owner))
    propagate(
        repo,
        owner,
        entities,
        run_rows,
        facts,
        sources,
        runs,
        redact_assistant,
        (*DERIVED_KINDS, "episode", "runtime_step"),
        recomputable,
        seed_entities,
        include_legacy=bool(source_ids),
    )
    spans, _ = owner_spans(repo, owner)
    redact_case_fields(repo, owner, spans, partial)
    refresh_source_indexes(repo, owner, spans)
    with repo.transaction(owner) as connection:
        if sources:
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE owner=%s AND kind='message' AND entity_id=ANY(%s)").format(
                    repo.table("core_embeddings")
                ),
                (owner, list(sources)),
            )
        if fact_ids:
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE owner=%s AND kind='fact' AND entity_id=ANY(%s)").format(
                    repo.table("core_embeddings")
                ),
                (owner, list(fact_ids)),
            )
        clear_runtime_outputs(repo, connection, owner, runs)
    return list(sources), list(runs), partial


def clear_runtime_outputs(repo: PostgresRepository, connection: Any, owner: str, runs: set[str]) -> None:
    if not runs:
        return
    connection.execute(
        sql.SQL("UPDATE {} SET output=NULL,error_code='SOURCE_REVOKED' WHERE owner=%s AND run_id=ANY(%s)").format(
            repo.table("core_run_steps")
        ),
        (owner, list(runs)),
    )
    connection.execute(
        sql.SQL("UPDATE {} SET payload='{{}}' WHERE owner=%s AND run_id=ANY(%s)").format(repo.table("core_run_events")),
        (owner, list(runs)),
    )

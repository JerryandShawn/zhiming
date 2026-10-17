"""Deterministic withdrawal of the new derived storage layers."""

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.projections import owner_spans, redact_ranges
from mingjing_core.memory.tokenize import searchable_data

from .privacy_closure import closure_rows, partial_sources, propagate

DERIVED_KINDS = ("thread_summary", "note", "profile_doc", "knowledge_gap", "followup", "reminder", "proposal")


def redact_assistant(repo, owner, message):
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


def refresh_source_indexes(repo, owner, spans):
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
    repo, owner, fact_ids, source_ids, run_ids=(), *, span_source_ids=(), recomputable=False, seed_entities=()
):
    facts, sources, runs = set(fact_ids), set(source_ids), set(run_ids)
    partial = partial_sources(repo, owner, facts, span_source_ids)
    sources.update(partial)
    sources.update(ident for _, ident in seed_entities)
    entities, run_rows = closure_rows(repo, owner, (*DERIVED_KINDS, "message", "episode", "interpretive_claim"))
    propagate(
        repo,
        owner,
        entities,
        run_rows,
        facts,
        sources,
        runs,
        redact_assistant,
        (*DERIVED_KINDS, "episode"),
        recomputable,
        seed_entities,
        include_legacy=bool(source_ids),
    )
    spans, _ = owner_spans(repo, owner)
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
        if runs:
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET output=NULL,error_code='SOURCE_REVOKED' WHERE owner=%s AND run_id=ANY(%s)"
                ).format(repo.table("core_run_steps")),
                (owner, list(runs)),
            )
            connection.execute(
                sql.SQL("UPDATE {} SET payload='{{}}' WHERE owner=%s AND run_id=ANY(%s)").format(
                    repo.table("core_run_events")
                ),
                (owner, list(runs)),
            )
    return list(sources), list(runs), partial

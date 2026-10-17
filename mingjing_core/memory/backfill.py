"""Idempotent metadata and successful-reply backfill; summaries expose no bodies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.projections import owner_spans, redact_ranges
from mingjing_core.memory.threads import message_fields, record_assistant
from mingjing_core.memory.tokenize import SEARCHABLE, searchable_data
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    # PostgreSQL rows contain heterogeneous, schema-dependent JSON payloads.
    from typing import Any

    from mingjing_core.application.memory import MemoryService
    from mingjing_core.repositories.postgres import PostgresRepository


def _rows(repo: PostgresRepository, owner: str) -> Iterator[dict[str, Any]]:
    cursor = ("", "")
    while True:
        with repo.transaction(owner) as connection:
            rows = connection.execute(
                sql.SQL(
                    "SELECT * FROM {} WHERE owner=%s AND (id,kind)>(%s,%s) AND status='active' "
                    "ORDER BY id,kind LIMIT 1000"
                ).format(repo.table("core_entities")),
                (owner, *cursor),
            ).fetchall()
        if not rows:
            return
        yield from rows
        cursor = rows[-1]["id"], rows[-1]["kind"]


def backfill_entities(repo: PostgresRepository, owner: str, *, apply: bool) -> dict[str, int | list[str]]:
    counts = {"message_metadata": 0, "search_tokens": 0, "invalid_time": 0, "sample_ids": []}
    spans, deleted = owner_spans(repo, owner)
    for row in _rows(repo, owner):
        data, changes = row["data"], {}
        if row["kind"] == "message":
            if row["id"] in deleted:
                continue
            stamp = history_instant(data.get("at")) or history_instant(row["created_at"])
            if history_instant(data.get("at")) is None:
                counts["invalid_time"] += 1
            desired = message_fields(
                row["subject"], stamp, data.get("origin_conversation_id", data.get("conversation_id", "default"))
            )
            changes.update({key: value for key, value in desired.items() if data.get(key) != value})
            counts["message_metadata"] += bool(changes)
        if row["kind"] in SEARCHABLE:
            projected = (
                dict(data, content=redact_ranges(data.get("content", ""), spans.get(row["id"], [])))
                if row["kind"] == "message"
                else data
            )
            tokens = searchable_data(row["kind"], projected).get("search_tokens", "")
            if data.get("search_tokens") != tokens:
                changes["search_tokens"] = tokens
                counts["search_tokens"] += 1
        if changes:
            if len(counts["sample_ids"]) < 5:
                counts["sample_ids"].append(row["id"])
            if apply:
                # Metadata is not a new original-source revision. Bumping it
                # would invalidate every existing SourceRef.version.
                with repo.transaction(owner) as connection:
                    connection.execute(
                        sql.SQL(
                            "UPDATE {} SET data=data||%s WHERE owner=%s AND kind=%s AND id=%s AND status='active'"
                        ).format(repo.table("core_entities")),
                        (Jsonb(changes), owner, row["kind"], row["id"]),
                    )
    return counts


def _run_context(
    repo: PostgresRepository,
    owner: str,
    run: dict[str, Any],
    revocations: Sequence[dict[str, Any]],
) -> tuple[set[str], dict[str, Any]] | None:
    sources = {key[8:] for key in run["state_version"] if key.startswith("message:")}
    sources.update(value for key in ("source_message_id", "message_id") if (value := run["request"].get(key)))
    facts = {key[5:] for key in run["state_version"] if key.startswith("fact:")}
    for revoked in revocations:
        if (
            (revoked["kind"] == "message" and revoked["entity_id"] in sources)
            or (revoked["kind"] == "fact" and revoked["entity_id"] in facts)
            or (revoked["kind"] == "source_span" and revoked["metadata"].get("message_id") in sources)
        ):
            return None
    try:
        messages = [repo.get(owner, "message", ident, include_deleted=True) for ident in sorted(sources)]
    except (EvidenceError, ScopeError):
        return None
    if not messages or any(
        message["status"] != "active" or message["subject_id"] != run["subject"] for message in messages
    ):
        return None
    candidates = [
        message
        for message in messages
        if message.get("role") == "user" and message.get("content") == run["request"].get("message")
    ]
    for key in ("source_message_id", "message_id"):
        if requested := run["request"].get(key):
            original = next((message for message in candidates if message["id"] == requested), None)
            return (sources, original) if original is not None else None
    exact = [message for message in candidates if message.get("source_id") == run["operation_id"]]
    if len(exact) == 1:
        return sources, exact[0]
    matching = [message for message in candidates if message.get("content") == run["request"].get("message")]
    # Ambiguous migration input is skipped rather than assigning a guessed channel.
    return (sources, matching[0]) if len(matching) == 1 else None


def backfill_replies(memory: MemoryService, owner: str, *, apply: bool) -> dict[str, int]:
    repo = memory.repo
    counts = {"assistant_created": 0, "assistant_existing": 0, "assistant_skipped": 0}
    revocations = repo.revocations(owner)
    with repo.transaction(owner) as connection:
        runs = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND status='succeeded' AND result IS NOT NULL ORDER BY created_at,id"
            ).format(repo.table("core_runs")),
            (owner,),
        ).fetchall()
        existing_ids = {
            row["id"]
            for row in connection.execute(
                sql.SQL("SELECT id FROM {} WHERE owner=%s AND kind='message'").format(repo.table("core_entities")),
                (owner,),
            ).fetchall()
        }
    for run in runs:
        context = _run_context(repo, owner, run, revocations)
        result = run["result"]
        if context is None or not isinstance(result.get("answer"), str) or not result["answer"]:
            counts["assistant_skipped"] += 1
            continue
        source_ids, source = context
        mode = run["request"].get("mode")
        kind = (
            ("brief" if run["request"].get("selection", {}).get("report_schedule_kind") == "daily" else "report")
            if mode == "scheduled_report"
            else "chat"
        )
        from mingjing_core.repositories.postgres import fingerprint

        ident = "msg_" + fingerprint([owner, "assistant", run["id"]])[:32]
        if ident in existing_ids:
            counts["assistant_existing"] += 1
            continue
        counts["assistant_created"] += 1
        if apply:
            record_assistant(
                memory,
                owner,
                run["subject"],
                "life:" + run["subject"],
                result["answer"],
                run_id=run["id"],
                kind=kind,
                used_fact_ids=result.get("cited_fact_ids", []),
                used_claim_ids=result.get("cited_claim_ids", []),
                source_ids=sorted(source_ids),
                channel=source.get("channel", "web"),
                at=run["updated_at"],
                case_ids=run["request"].get("case_ids", []),
                conversation_id=run["request"].get("conversation_id", "default"),
            )
            existing_ids.add(ident)
    return counts


def backfill(memory: MemoryService, owner: str, *, apply: bool = False) -> dict[str, str | int | list[str]]:
    repo = memory.repo
    with repo.transaction(owner):
        repo.assert_scope(owner)
        # The owner lock covers dry-run consistency and the complete apply, so
        # interruption rolls back both metadata and newly written replies.
        entities = backfill_entities(repo, owner, apply=apply)
        replies = backfill_replies(memory, owner, apply=apply)
    return {"mode": "apply" if apply else "dry-run", **entities, **replies}

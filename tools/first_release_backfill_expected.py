"""Private, value-by-value expectations from injected native backfill projections."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

METADATA = frozenset({"thread_id", "at_ms", "origin_conversation_id", "search_tokens"})
WRITES = ("message_metadata", "search_tokens", "assistant_created")


class BackfillEffectRejected(RuntimeError):
    """Only fixed error codes cross the component boundary."""


def require(value: Any, code: str) -> None:
    if not value:
        raise BackfillEffectRejected(code)


@dataclass(frozen=True)
class BackfillBindings:
    """Callables are supplied by the caller; this is not candidate authentication."""

    memory_factory: Callable[[Any], Any] = field(repr=False)
    module: Any = field(repr=False)
    tokenized_payload: Callable[..., dict] = field(repr=False)
    fingerprint: Callable[[Any], str] = field(repr=False)


@dataclass(frozen=True)
class ExpectedReply:
    identifier: str
    subject: str
    operation: str
    payload: dict[str, Any] = field(repr=False)
    operation_fingerprint: str = field(repr=False)


@dataclass(frozen=True)
class ExpectedBackfill:
    owner: str
    counts: dict[str, Any] = field(repr=False)
    metadata: dict[tuple[str, str, str], dict[str, Any]] = field(repr=False)
    replies: tuple[ExpectedReply, ...] = field(repr=False)


def metadata_for(row: dict, module: Any, spans: dict, deleted: set) -> tuple[dict, int, int]:
    data, changes, invalid = row["data"], {}, 0
    if row["kind"] == "message" and not module.is_private(data):
        if row["id"] in deleted:
            return {}, 0, 0
        at = module.history_instant(data.get("at"))
        invalid = int(at is None)
        desired = module.message_fields(
            row["subject"],
            at or module.history_instant(row["created_at"]),
            data.get("origin_conversation_id", data.get("conversation_id", "default")),
        )
        changes.update({key: value for key, value in desired.items() if data.get(key) != value})
    message_changes = int(bool(changes))
    if row["kind"] in module.SEARCHABLE:
        projected = (
            dict(data, content=module.redact_ranges(data.get("content", ""), spans.get(row["id"], [])))
            if row["kind"] == "message"
            else data
        )
        tokens = module.searchable_data(row["kind"], projected).get("search_tokens", "")
        if data.get("search_tokens") != tokens:
            changes["search_tokens"] = tokens
    require(set(changes) <= METADATA, "BACKFILL_UNEXPECTED_METADATA_PLAN")
    return changes, message_changes, invalid


def reply_value(run: dict, result: dict, sources: set, source: dict, facts: list, claims: list, module: Any) -> dict:
    selection = run["request"].get("selection", {})
    scheduled = run["request"].get("mode") == "scheduled_report"
    kind = ("brief" if selection.get("report_schedule_kind") == "daily" else "report") if scheduled else "chat"
    conversation = run["request"].get("conversation_id", "default")
    stamp = run["updated_at"]
    return dict(
        module.message_fields(run["subject"], stamp, conversation),
        content=result["answer"],
        role="assistant",
        channel=source.get("channel", "web"),
        at=stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp),
        source_id=run["id"],
        run_id=run["id"],
        kind=kind,
        conversation_id=conversation,
        case_ids=list(run["request"].get("case_ids", [])),
        source_ids=sorted(sources),
        used_fact_ids=list(facts),
        used_claim_ids=list(claims),
        policy={"origin": "system", "run_context": False},
    )


def expected_reply(
    repo: Any, owner: str, run: dict, revocations: list, bindings: BackfillBindings
) -> ExpectedReply | None:
    module = bindings.module
    context = module._run_context(repo, owner, run, revocations)
    if context is None:
        return None
    sources, source = context
    try:
        result = module._reply(run)
        facts, claims = module._lineage(repo, owner, run, result, sources)
    except (module.EvidenceError, module.ScopeError, TypeError, ValueError, KeyError, AttributeError):
        return None
    identifier = "msg_" + bindings.fingerprint([owner, "assistant", run["id"]])[:32]
    value = reply_value(run, result, sources, source, facts, claims, module)
    operation = "assistant:" + run["id"] + ":" + bindings.fingerprint(value)
    payload = bindings.tokenized_payload(repo, owner, "message", identifier, value)
    return ExpectedReply(
        identifier,
        run["subject"],
        operation,
        payload,
        bindings.fingerprint(["message", identifier, run["subject"], None, value]),
    )


def expected_backfill(
    repo: Any, owner: str, rows: dict[str, list[dict]], bindings: BackfillBindings
) -> ExpectedBackfill:
    counts = dict(message_metadata=0, search_tokens=0, invalid_time=0, sample_ids=[])
    counts.update(assistant_created=0, assistant_existing=0, assistant_skipped=0)
    entities = rows["core_entities"]
    spans, deleted = bindings.module.owner_spans(repo, owner)
    metadata = {}
    active = sorted(
        (row for row in entities if row["owner"] == owner and row["status"] == "active"),
        key=lambda row: (row["id"], row["kind"]),
    )
    for row in active:
        changes, changed, invalid = metadata_for(row, bindings.module, spans, deleted)
        counts["message_metadata"] += changed
        counts["invalid_time"] += invalid
        counts["search_tokens"] += int("search_tokens" in changes)
        if changes:
            metadata[(owner, row["kind"], row["id"])] = changes
            if len(counts["sample_ids"]) < 5:
                counts["sample_ids"].append(row["id"])
    existing = {row["id"] for row in entities if row["owner"] == owner and row["kind"] == "message"}
    revocations = repo.revocations(owner)
    runs = sorted(
        (
            row
            for row in rows["core_runs"]
            if row["owner"] == owner and row["status"] == "succeeded" and row["result"] is not None
        ),
        key=lambda row: (row["created_at"], row["id"]),
    )
    return _replies(repo, owner, runs, existing, revocations, counts, metadata, bindings)


def _replies(
    repo: Any,
    owner: str,
    runs: list[dict],
    existing: set[str],
    revocations: list[dict],
    counts: dict[str, Any],
    metadata: dict[tuple[str, str, str], dict],
    bindings: BackfillBindings,
) -> ExpectedBackfill:
    replies = []
    for run in runs:
        reply = expected_reply(repo, owner, deepcopy(run), revocations, bindings)
        if reply is None:
            counts["assistant_skipped"] += 1
        elif reply.identifier in existing:
            counts["assistant_existing"] += 1
        else:
            counts["assistant_created"] += 1
            replies.append(reply)
            existing.add(reply.identifier)
    return ExpectedBackfill(owner, counts, metadata, tuple(replies))

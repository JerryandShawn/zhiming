"""Idempotent metadata and successful-reply backfill; summaries expose no bodies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.private import is_private
from mingjing_core.memory.projections import owner_spans, redact_ranges
from mingjing_core.memory.threads import message_fields, record_assistant
from mingjing_core.memory.tokenize import SEARCHABLE, searchable_data
from mingjing_core.repositories.dependencies import entity_dependency
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
        if row["kind"] == "message" and not is_private(data):
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
    if is_private(run["request"]) or str(run.get("thread_id", "")).startswith("incognito:"):
        return None
    sources = {key[8:] for key in run["state_version"] if key.startswith("message:")}
    sources.update(value for key in ("source_message_id", "message_id") if (value := run["request"].get(key)))
    sources.update(run["request"].get("source_message_ids", []))
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
        message["status"] != "active"
        or message["subject_id"] != run["subject"]
        or is_private(message)
        or run["state_version"].get("message:" + message["id"], message["revision"]) != message["revision"]
        for message in messages
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


def _reply(run: dict[str, Any]) -> dict[str, Any]:
    # A top-level import would cycle through application.__init__ -> MemoryService.
    from mingjing_core.application.read_result import read_result

    result = read_result(run["result"])
    schema = result["schema_version"]
    if (
        result.get("schema", schema) != schema
        or result["validation"].get("schema", schema) != schema
        or result["validation"].get("valid", True) is not True
    ):
        raise EvidenceError("回填结果版本或验证状态不符")
    meta = result.get("meta", {})
    identity = meta.get("core_run")
    if schema == "core4.0" and (not identity or run.get("runtime") != "v4"):
        raise EvidenceError("core4回填缺少持久运行身份")
    if identity is not None and (
        identity.get("run_id") != run["id"]
        or identity.get("operation_id") != run["operation_id"]
        or meta.get("subject_id", run["subject"]) != run["subject"]
    ):
        raise EvidenceError("回填结果运行身份不符")
    return result


def _entity(repo: PostgresRepository, owner: str, run: dict, kind: str, ident: str) -> dict:
    if not isinstance(ident, str) or not 1 <= len(ident) <= 200:
        raise EvidenceError("回填引用标识无效")
    row = repo.get(owner, kind, ident, include_deleted=True)
    if row["status"] != "active" or row["subject_id"] != run["subject"] or is_private(row):
        raise EvidenceError("回填引用不属于有效人物来源")
    if repo.is_revoked(owner, kind, ident):
        raise EvidenceError("回填引用已撤销")
    return row


def _source_refs(repo: PostgresRepository, owner: str, run: dict, refs: list, sources: set[str]) -> None:
    if not isinstance(refs, list) or len(refs) > 1000:
        raise EvidenceError("回填原话范围无效")
    for ref in refs:
        if not isinstance(ref, dict) or not {"message_id", "version", "start", "end", "quote"} <= ref.keys():
            raise EvidenceError("回填原话缺少完整区间")
        source = _entity(repo, owner, run, "message", ref["message_id"])
        start, end = ref["start"], ref["end"]
        if (
            source.get("role") != "user"
            or source.get("policy", {}).get("origin") != "current_user"
            or source.get("policy", {}).get("run_context") is not True
            or type(ref["version"]) is not int
            or source["revision"] != ref["version"]
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(source.get("content", ""))
            or source["content"][start:end] != ref["quote"]
            or any(
                row["kind"] == "source_span" and row["metadata"].get("message_id") == source["id"]
                for row in repo.revocations(owner)
            )
        ):
            raise EvidenceError("回填原话已改变或撤销")
        sources.add(source["id"])


def _fact_sources(repo: PostgresRepository, owner: str, run: dict, result: dict, ident: str, sources: set) -> None:
    if result["schema_version"] == "core3.0" and ident.startswith("current_source_"):
        evidence = [
            item
            for item in result.get("evidence", [])
            if item.get("ref") == "source:" + ident and item.get("context_only") is True
        ]
        if len(evidence) != 1 or not evidence[0].get("source_refs"):
            raise EvidenceError("临时事实缺少已提交原话依据")
        if ident not in result.get("meta", {}).get("injected_ids", []) or any(
            run["state_version"].get("message:" + ref["message_id"]) != ref["version"]
            for ref in evidence[0]["source_refs"]
        ):
            raise EvidenceError("临时事实不在原运行采用范围")
        _source_refs(repo, owner, run, evidence[0]["source_refs"], sources)
        return
    row = _entity(repo, owner, run, "fact", ident)
    if (
        run["state_version"].get("fact:" + ident) != row["revision"]
        or row.get("consent") != "granted"
        or not row.get("source_refs")
    ):
        raise EvidenceError("回填事实缺少真实采用版本")
    _source_refs(repo, owner, run, row["source_refs"], sources)


def _claim_row(repo: PostgresRepository, owner: str, run: dict, result: dict, ident: str) -> dict:
    if result["schema_version"] == "core4.0":
        row = _entity(repo, owner, run, "interpretive_claim", ident)
        if (
            type(row.get("epoch")) is not int
            or row["epoch"] != run["retry_epoch"]
            or run["state_version"].get(entity_dependency("interpretive_claim", ident)) != row["revision"]
        ):
            raise EvidenceError("core4引用缺少采用版本")
    else:
        native = run["id"] + ":e" + str(run["retry_epoch"]) + ":" + ident
        try:
            row = _entity(repo, owner, run, "interpretive_claim", native)
        except ScopeError:
            if run["retry_epoch"] != 0:
                raise
            row = _entity(repo, owner, run, "interpretive_claim", run["id"] + ":" + ident)
        if row.get("claim", {}).get("claim_id") != ident:
            raise EvidenceError("core3引用不是本轮真实专业声明")
    if row.get("run_id") != run["id"]:
        raise EvidenceError("回填引用不属于原运行")
    return row


def _lineage(repo: PostgresRepository, owner: str, run: dict, result: dict, sources: set) -> tuple[list, list]:
    prefix = "used" if result["schema_version"] == "core4.0" else "cited"
    facts, claims = result.get(prefix + "_fact_ids", []), result.get(prefix + "_claim_ids", [])
    if any(
        not isinstance(values, list)
        or len(values) > 1000
        or any(not isinstance(value, str) or not 1 <= len(value) <= 200 for value in values)
        for values in (facts, claims)
    ):
        raise EvidenceError("回填引用列表无效")
    for ident in facts:
        _fact_sources(repo, owner, run, result, ident, sources)
    for ident in claims:
        row = _claim_row(repo, owner, run, result, ident)
        _source_refs(repo, owner, run, row.get("source_refs", []), sources)
        for source_id in row.get("source_ids", []):
            source = _entity(repo, owner, run, "message", source_id)
            if source.get("role") != "user":
                raise EvidenceError("专业引用不是用户原话")
            sources.add(source_id)
        for fact_id in row.get("used_fact_ids", []):
            _fact_sources(repo, owner, run, result, fact_id, sources)
    return facts, claims


def _record_reply(
    memory: MemoryService,
    owner: str,
    run: dict[str, Any],
    result: dict[str, Any],
    source_ids: set[str],
    source: dict[str, Any],
    facts: list[str],
    claims: list[str],
) -> None:
    mode = run["request"].get("mode")
    kind = (
        ("brief" if run["request"].get("selection", {}).get("report_schedule_kind") == "daily" else "report")
        if mode == "scheduled_report"
        else "chat"
    )
    record_assistant(
        memory,
        owner,
        run["subject"],
        "life:" + run["subject"],
        result["answer"],
        run_id=run["id"],
        kind=kind,
        used_fact_ids=facts,
        used_claim_ids=claims,
        source_ids=sorted(source_ids),
        channel=source.get("channel", "web"),
        at=run["updated_at"],
        case_ids=run["request"].get("case_ids", []),
        conversation_id=run["request"].get("conversation_id", "default"),
    )


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
        if context is None:
            counts["assistant_skipped"] += 1
            continue
        source_ids, source = context
        try:
            result = _reply(run)
            facts, claims = _lineage(repo, owner, run, result, source_ids)
        except (EvidenceError, ScopeError, TypeError, ValueError, KeyError, AttributeError):
            counts["assistant_skipped"] += 1
            continue
        from mingjing_core.repositories.postgres import fingerprint

        ident = "msg_" + fingerprint([owner, "assistant", run["id"]])[:32]
        if ident in existing_ids:
            counts["assistant_existing"] += 1
            continue
        counts["assistant_created"] += 1
        if apply:
            _record_reply(memory, owner, run, result, source_ids, source, facts, claims)
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

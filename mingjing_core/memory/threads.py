"""Program-authored replies have lineage and can never grant user consent."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

from .private import is_private
from .projections import redact_ranges

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    # Entity payloads and source references retain schema-dependent JSON values.
    from typing import Any

    from mingjing_core.application.memory import MemoryService
    from mingjing_core.repositories.postgres import PostgresRepository


def message_fields(subject: str, at: datetime | str | None, conversation_id: str) -> dict[str, str | int]:
    stamp = history_instant(at)
    if stamp is None:
        raise ValueError("消息时间无效")
    return {
        "thread_id": "life:" + subject,
        "at_ms": int(stamp.timestamp() * 1000),
        "origin_conversation_id": conversation_id,
    }


def record_assistant(
    memory: MemoryService,
    owner: str,
    subject: str,
    thread_id: str,
    text: str,
    *,
    run_id: str,
    kind: str = "chat",
    used_fact_ids: Iterable[str] = (),
    used_claim_ids: Iterable[str] = (),
    source_ids: Iterable[str] = (),
    channel: str,
    at: datetime | str | None = None,
    case_ids: Iterable[str] = (),
    conversation_id: str = "default",
) -> dict[str, Any]:
    if (
        not isinstance(text, str)
        or not 1 <= len(text) <= 200000
        or kind not in ("chat", "brief", "followup", "report", "system_note")
    ):
        raise ValueError("助手消息内容或种类无效")
    if thread_id != "life:" + subject or not isinstance(run_id, str) or not run_id:
        raise ScopeError("助手消息线程或稳定运行 ID 无效")
    if re.search(r"sk-[A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY-----", text):
        raise EvidenceError("Credentials cannot be stored in assistant memory")
    repo = memory.repo
    repo.assert_scope(owner, subject)
    ident = "msg_" + fingerprint([owner, "assistant", run_id])[:32]
    stamp = at or get_clock().now()
    value = dict(
        message_fields(subject, stamp, conversation_id),
        content=text,
        role="assistant",
        channel=channel,
        at=stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp),
        source_id=run_id,
        run_id=run_id,
        kind=kind,
        conversation_id=conversation_id,
        case_ids=list(case_ids),
        source_ids=list(source_ids),
        used_fact_ids=list(used_fact_ids),
        used_claim_ids=list(used_claim_ids),
        policy={"origin": "system", "run_context": False},
    )
    return _persist_assistant(repo, owner, subject, ident, run_id, value)


def _persist_assistant(
    repo: PostgresRepository, owner: str, subject: str, ident: str, run_id: str, value: dict[str, Any]
) -> dict[str, Any]:
    with repo.transaction(owner):
        if repo.is_revoked(owner, "message", ident):
            raise EvidenceError("Withdrawn assistant reply cannot be restored")
        try:
            old = repo.get(owner, "message", ident, include_deleted=True)
        except ScopeError:
            old = None
        if old and old.get("redacted"):
            raise EvidenceError("Withdrawn assistant reply cannot be restored")
        if old:
            value["at"], value["at_ms"] = old["at"], old["at_ms"]
            if all(old.get(key) == item for key, item in value.items()):
                return old
        operation = "assistant:" + run_id + ":" + fingerprint(value)
        return repo.put(
            owner,
            "message",
            ident,
            value,
            subject=subject,
            expected_revision=old["revision"] if old else 0,
            operation_id=operation,
        )


def project_sources(
    memory: MemoryService,
    owner: str,
    rows: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    selected: set[str],
    *,
    private_thread: str | None = None,
) -> list[dict[str, Any]]:
    spans = {}
    for row in memory.repo.revocations(owner) if rows else []:
        if row["kind"] == "source_span":
            span = row["metadata"]
            spans.setdefault(span.get("message_id"), []).append(span)
    result = []
    for row in rows:
        if is_private(row) and row.get("thread_id") != private_thread:
            continue
        cases = set(row.get("case_ids", []))
        if cases and not selected.intersection(cases):
            continue
        text = redact_ranges(row.get("content", ""), spans.get(row["id"], []))
        source = dict(row, content=text)
        if cases - selected:
            quotes = [
                fact.get("content", "")
                for fact in facts
                if any(ref.get("message_id") == row["id"] for ref in fact.get("source_refs", []))
                and fact.get("content") in text
            ]
            if not quotes:
                continue
            source.update(content="\n".join(dict.fromkeys(quotes)), context_projection="selected_fact_quotes")
        result.append(source)
    return result

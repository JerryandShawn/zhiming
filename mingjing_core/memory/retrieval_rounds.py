"""Conversation rounds and assistant notes remain attributable to assistant message IDs."""

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from .retrieval_types import SearchSource, SearchUnit, SourceRef, authorized, instant


@dataclass(frozen=True)
class MessageForRound:
    id: str
    owner_id: str
    subject_id: str
    role: str
    text: str = field(repr=False)
    at: datetime
    revision: int = 1
    thread_id: str = "default"
    conversation_id: str = "default"
    active: bool = True
    redacted: bool = False
    incognito: bool = False

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant"} or not self.id:
            raise ValueError("轮索引消息无效")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("轮索引消息版本无效")
        if not all(type(value) is bool for value in (self.active, self.redacted, self.incognito)):
            raise ValueError("轮索引消息状态无效")
        object.__setattr__(self, "at", instant(self.at))


def _ident(prefix: str, *parts: str) -> str:
    # Delimited components prevent concatenation collisions between source IDs.
    return prefix + hashlib.sha256("\0".join(parts).encode()).hexdigest()[:32]


def _round(user: MessageForRound, assistant: MessageForRound) -> SearchUnit:
    return SearchUnit(
        _ident("round_", user.owner_id, user.subject_id, user.id, assistant.id),
        user.owner_id,
        user.subject_id,
        "round",
        f"用户：{user.text}\n明镜：{assistant.text}",
        assistant.at,
        origin="assistant_claim",
        source_refs=(SourceRef(user.id, user.revision), SourceRef(assistant.id, assistant.revision)),
    )


def build_rounds(
    messages: Iterable[MessageForRound], *, source_state: Iterable[SearchSource]
) -> tuple[SearchUnit, ...]:
    sources, pending, result = tuple(source_state), {}, []
    ordered = sorted(messages, key=lambda message: (message.at, message.id))
    for message in ordered:
        key = (message.owner_id, message.subject_id, message.thread_id, message.conversation_id)
        if not message.active or message.redacted or message.incognito:
            pending.pop(key, None)
        elif message.role == "user":
            pending[key] = message
        elif (user := pending.pop(key, None)) is not None:
            unit = _round(user, message)
            if authorized(unit, unit.owner_id, unit.subject_id, sources):
                result.append(unit)
    return tuple(result)


def assistant_claim_candidate(
    message: MessageForRound,
    summary: str,
    *,
    source_state: Iterable[SearchSource],
    presented_options: bool = False,
    chart_judgment: bool = False,
) -> SearchUnit | None:
    if message.role != "assistant" or not message.active or message.redacted or message.incognito:
        return None
    chart = chart_judgment and bool(re.search(r"〔[cr][1-9]\d*〕", message.text))
    advice = bool(re.search(r"建议你|建议您|我建议", message.text))
    if not (presented_options or chart or advice) or not summary.strip():
        return None
    unit = SearchUnit(
        _ident("claim_", message.owner_id, message.subject_id, message.id),
        message.owner_id,
        message.subject_id,
        "note",
        summary,
        message.at,
        origin="assistant_claim",
        source_refs=(SourceRef(message.id, message.revision),),
    )
    return unit if authorized(unit, unit.owner_id, unit.subject_id, tuple(source_state)) else None


@dataclass(frozen=True)
class InvalidationPlan:
    owner_id: str
    subject_id: str
    withdrawn_source_ids: tuple[str, ...]
    remove_unit_ids: tuple[str, ...]
    reason: str = "source_withdrawn"


def invalidate_sources(
    owner: str, subject: str, withdrawn: Iterable[str], units: Iterable[SearchUnit]
) -> InvalidationPlan:
    """A plan only; callers also remove embeddings/tokens inside the authoritative transaction."""
    identifiers = frozenset(withdrawn)
    affected = sorted(
        unit.id
        for unit in units
        if unit.owner_id == owner
        and unit.subject_id == subject
        and any(ref.id in identifiers for ref in unit.source_refs)
    )
    return InvalidationPlan(owner, subject, tuple(sorted(identifiers)), tuple(affected))

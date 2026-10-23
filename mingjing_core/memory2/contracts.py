"""Immutable, private in-memory contracts; these are not a persistence authority."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from .validation import frozen_tuple, require_bool, require_int, require_text, unique


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("memory_time_must_be_aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class MemoryScope:
    owner_id: str
    subject_id: str

    def __post_init__(self) -> None:
        require_text(self.owner_id, self.subject_id)


@dataclass(frozen=True)
class MemorySource:
    id: str
    owner_id: str
    subject_id: str
    text: str = field(repr=False)
    at: datetime
    role: str = "user"
    revision: int = 1
    active: bool = True
    revoked: bool = False
    incognito: bool = False
    origin: str = "current_user"
    optout: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "at", utc(self.at))
        require_text(self.id, self.owner_id, self.subject_id, self.role, self.origin)
        require_int(self.revision, 1)
        require_bool(self.active, self.revoked, self.incognito, self.optout)
        if not isinstance(self.text, str):
            raise ValueError("memory_text_invalid")


@dataclass(frozen=True)
class SourceAnchor:
    source_id: str
    revision: int
    start: int
    end: int
    quote: str = field(repr=False)

    def __post_init__(self) -> None:
        require_text(self.source_id, self.quote)
        require_int(self.revision, 1)
        require_int(self.start)
        require_int(self.end, 1)
        if self.end <= self.start:
            raise ValueError("memory_anchor_interval_invalid")

    @property
    def quote_fingerprint(self) -> str:
        return sha256(self.quote.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryFact:
    id: str
    owner_id: str
    subject_id: str
    kind: str
    text: str = field(repr=False)
    source_ids: tuple[str, ...]
    said_at: datetime
    recorded_at: datetime
    anchors: tuple[SourceAnchor, ...] = field(default=(), repr=False)
    origin: str = "user"
    slot: str | None = None
    value: str | None = field(default=None, repr=False)
    event_at: datetime | None = None
    event_end: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    status: str = "active"
    supersedes: str | None = None
    superseded_by: str | None = None
    revision: int = 1
    pinned: bool = False
    edited: bool = False
    importance: float = 0.5
    source_valid: bool = True

    def __post_init__(self) -> None:
        require_text(self.id, self.owner_id, self.subject_id, self.kind, self.text)
        require_int(self.revision, 1)
        require_bool(self.pinned, self.edited, self.source_valid)
        object.__setattr__(self, "source_ids", frozen_tuple(self.source_ids, str))
        object.__setattr__(self, "anchors", frozen_tuple(self.anchors, SourceAnchor))
        unique(self.source_ids)
        for name in (
            "said_at",
            "recorded_at",
            "event_at",
            "event_end",
            "valid_from",
            "valid_to",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, utc(value))
        if type(self.importance) not in (int, float) or not 0 <= self.importance <= 1:
            raise ValueError("memory_fact_invalid")
        if self.status not in {"active", "archived", "retired", "deleted", "proposal"}:
            raise ValueError("memory_status_invalid")
        if self.origin not in {"user", "assistant_claim"}:
            raise ValueError("memory_origin_invalid")
        for value in (self.slot, self.value, self.supersedes, self.superseded_by):
            if value is not None and not isinstance(value, str):
                raise ValueError("memory_value_invalid")
        if self.valid_from is None:
            object.__setattr__(self, "valid_from", self.said_at)
        if self.event_end is not None and self.event_at is not None and self.event_end < self.event_at:
            raise ValueError("memory_event_interval_invalid")
        if self.valid_to is not None and self.valid_from is not None and self.valid_to < self.valid_from:
            raise ValueError("memory_validity_interval_invalid")


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    fingerprint: str
    status: str = "applied"
    result_ids: tuple[str, ...] = ()
    undo_of: str | None = None

    def __post_init__(self) -> None:
        require_text(self.operation_id, self.fingerprint)
        if self.status not in {"applied", "undone"}:
            raise ValueError("memory_operation_invalid")
        object.__setattr__(self, "result_ids", frozen_tuple(self.result_ids, str))


@dataclass(frozen=True)
class MemorySnapshot:
    scope: MemoryScope
    facts: tuple[MemoryFact, ...] = ()
    sources: tuple[MemorySource, ...] = field(default=(), repr=False)
    operations: tuple[OperationRecord, ...] = ()
    revision: int = 0
    source_epoch: int = 0
    asked_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise ValueError("memory_scope_required")
        require_int(self.revision)
        require_int(self.source_epoch)
        for name, expected in (
            ("facts", MemoryFact),
            ("sources", MemorySource),
            ("operations", OperationRecord),
        ):
            object.__setattr__(self, name, frozen_tuple(getattr(self, name), expected))
        object.__setattr__(self, "asked_keys", frozen_tuple(self.asked_keys, str))
        unique(item.id for item in self.facts)
        unique(item.id for item in self.sources)
        unique(item.operation_id for item in self.operations)

    def fact(self, fact_id: str) -> MemoryFact | None:
        return next((item for item in self.facts if item.id == fact_id), None)

    def source(self, source_id: str) -> MemorySource | None:
        return next((item for item in self.sources if item.id == source_id), None)


@dataclass(frozen=True)
class MemorySettings:
    auto_save_categories: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.auto_save_categories, (frozenset, set, tuple, list)):
            raise ValueError("memory_categories_invalid")
        require_text(*self.auto_save_categories)
        object.__setattr__(self, "auto_save_categories", frozenset(self.auto_save_categories))


@dataclass(frozen=True)
class Confirmation:
    scope: MemoryScope
    source_id: str
    source_revision: int
    quote_fingerprint: str
    categories: frozenset[str]
    decision: Literal["granted", "declined"]
    at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "at", utc(self.at))
        require_int(self.source_revision, 1)
        require_text(self.source_id, self.quote_fingerprint)
        if self.decision not in {"granted", "declined"} or not isinstance(self.scope, MemoryScope):
            raise ValueError("memory_confirmation_invalid")
        if not isinstance(self.categories, (set, frozenset, tuple, list)):
            raise ValueError("memory_categories_invalid")
        require_text(*self.categories)
        object.__setattr__(self, "categories", frozenset(self.categories))


@dataclass(frozen=True)
class PolicyDecision:
    action: Literal["save", "proposal", "stop", "reject", "profile_confirm"]
    categories: tuple[str, ...] = ()
    ask_required: bool = False
    question_key: str | None = None
    reason: str = ""

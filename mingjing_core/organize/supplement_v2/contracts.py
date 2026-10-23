"""Pure review projections. Host adapters remain responsible for authenticated snapshots and clicks."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from mingjing_core.memory2.contracts import MemoryScope, MemorySource, SourceAnchor, utc
from mingjing_core.memory2.validation import frozen_tuple, require_bool, require_int, require_text, unique

LABEL_FIELDS = frozenset({"space_id", "topic_id", "space_secondary", "route_source", "route_confidence"})
KINDS = frozenset({"message", "fact", "note", "case", "draw", "legacy_archive"})


class SupplementConflict(ValueError):
    """Fixed reason only: no source text, goal, title, or labels in exceptions."""


def labels(values: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(values, Mapping) or set(values) - LABEL_FIELDS:
        raise SupplementConflict("label_fields_invalid")
    for key, value in values.items():
        if key == "route_confidence":
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise SupplementConflict("label_confidence_invalid")
        elif value is not None and (type(value) is not str or not value.strip()):
            raise SupplementConflict("label_identifier_invalid")
    if values.get("route_source") not in {None, "rule", "embedding", "model", "user", "migration"}:
        raise SupplementConflict("label_source_invalid")
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class EntityRecord:
    id: str
    scope: MemoryScope
    kind: str
    text: str = field(repr=False)
    said_at: datetime
    anchors: tuple[SourceAnchor, ...] = field(repr=False)
    revision: int = 1
    labels: Mapping[str, object] = field(default_factory=dict, repr=False)
    active: bool = True
    current: bool = True
    revoked: bool = False
    incognito: bool = False
    origin: str = "user"
    sensitive_categories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text(self.id, self.text)
        if not isinstance(self.scope, MemoryScope) or self.kind not in KINDS:
            raise SupplementConflict("entity_kind_or_scope_invalid")
        if self.origin not in {"user", "assistant_claim"} or (self.origin == "assistant_claim" and self.kind != "note"):
            raise SupplementConflict("entity_origin_invalid")
        require_int(self.revision, 1)
        require_bool(self.active, self.current, self.revoked, self.incognito)
        object.__setattr__(self, "said_at", utc(self.said_at))
        object.__setattr__(self, "anchors", frozen_tuple(self.anchors, SourceAnchor))
        object.__setattr__(self, "labels", labels(self.labels))
        categories = frozen_tuple(self.sensitive_categories, str)
        require_text(*categories)
        unique(categories)
        object.__setattr__(self, "sensitive_categories", tuple(sorted(categories)))


@dataclass(frozen=True)
class TopicRecord:
    id: str
    scope: MemoryScope
    last_at: datetime
    anchors: tuple[SourceAnchor, ...] = field(repr=False)
    revision: int = 1
    status: str = "open"
    title: str = field(default="", repr=False)
    active: bool = True
    current: bool = True
    revoked: bool = False
    incognito: bool = False

    def __post_init__(self) -> None:
        require_text(self.id)
        if not isinstance(self.scope, MemoryScope) or self.status not in {"open", "archived", "case"}:
            raise SupplementConflict("topic_status_or_scope_invalid")
        if type(self.title) is not str:
            raise SupplementConflict("topic_title_invalid")
        require_int(self.revision, 1)
        require_bool(self.active, self.current, self.revoked, self.incognito)
        object.__setattr__(self, "last_at", utc(self.last_at))
        object.__setattr__(self, "anchors", frozen_tuple(self.anchors, SourceAnchor))


@dataclass(frozen=True)
class ProjectionOperation:
    id: str
    fingerprint: str
    state: str = "applied"

    def __post_init__(self) -> None:
        require_text(self.id, self.fingerprint)
        if self.state not in {"applied", "undone"}:
            raise SupplementConflict("operation_state_invalid")


@dataclass(frozen=True)
class SupplementSnapshot:
    scope: MemoryScope
    entities: tuple[EntityRecord, ...] = field(default=(), repr=False)
    topics: tuple[TopicRecord, ...] = field(default=(), repr=False)
    sources: tuple[MemorySource, ...] = field(default=(), repr=False)
    revision: int = 0
    source_epoch: int = 0
    operations: tuple[ProjectionOperation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise SupplementConflict("snapshot_scope_invalid")
        require_int(self.revision)
        require_int(self.source_epoch)
        for name, cls in (
            ("entities", EntityRecord),
            ("topics", TopicRecord),
            ("sources", MemorySource),
            ("operations", ProjectionOperation),
        ):
            values = frozen_tuple(getattr(self, name), cls)
            unique(item.id for item in values)
            object.__setattr__(self, name, values)

    def entity(self, identity: str) -> EntityRecord | None:
        return next((item for item in self.entities if item.id == identity), None)

    def topic(self, identity: str) -> TopicRecord | None:
        return next((item for item in self.topics if item.id == identity), None)


@dataclass(frozen=True)
class ReviewApproval:
    scope: MemoryScope
    fingerprint: str
    decision: str = "approved"
    actor: str = "user"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise SupplementConflict("review_scope_invalid")
        require_text(self.fingerprint)
        if self.decision not in {"approved", "declined"} or self.actor != "user":
            raise SupplementConflict("review_approval_invalid")


@dataclass(frozen=True)
class SensitiveGrant:
    scope: MemoryScope
    entity_id: str
    entity_revision: int
    evidence_fingerprint: str
    categories: tuple[str, ...]
    decision: str = "granted"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise SupplementConflict("consent_scope_invalid")
        require_text(self.entity_id, self.evidence_fingerprint)
        require_int(self.entity_revision, 1)
        values = frozen_tuple(self.categories, str)
        require_text(*values)
        unique(values)
        object.__setattr__(self, "categories", tuple(sorted(values)))
        if self.decision not in {"granted", "declined"}:
            raise SupplementConflict("consent_decision_invalid")

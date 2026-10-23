"""Private store results and metadata; operation ledgers never enter the public SSE envelope."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .event_models import RunEvent, RunScope


class EventStoreError(ValueError):
    """Fixed machine reasons only, without private payloads."""


class EventStoreConflict(EventStoreError):
    """An operation identity or sequence was reused with incompatible content."""


class EventCursorError(EventStoreError):
    """Unknown and foreign cursors share one error; neither reveals event ownership."""


@dataclass(frozen=True)
class AppendResult:
    event: RunEvent = field(repr=False)
    replayed: bool = False


@dataclass(frozen=True)
class ReplayPage:
    events: tuple[RunEvent, ...] = field(repr=False)
    next_seq: int
    has_more: bool = False


@dataclass(frozen=True)
class StoredOperation:
    fingerprint: str
    row: Mapping[str, object] = field(repr=False)


@dataclass(frozen=True)
class StoredEventMetadata:
    scope: RunScope
    seq: int
    type: str
    created_at: datetime
    fingerprint: str


@dataclass(frozen=True)
class EventColumns:
    """The existing P2 table has kind/payload; type/data requires an explicit alternate mapping."""

    owner: str = "owner"
    run_id: str = "run_id"
    seq: str = "seq"
    type: str = "kind"
    data: str = "payload"
    created_at: str = "created_at"

    def __post_init__(self) -> None:
        values = tuple(getattr(self, name) for name in self.__dataclass_fields__)
        if any(not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value) for value in values):
            raise EventStoreError("event_column_invalid")
        if len(set(values)) != len(values):
            raise EventStoreError("event_columns_must_be_distinct")

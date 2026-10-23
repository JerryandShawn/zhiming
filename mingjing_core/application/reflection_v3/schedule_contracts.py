"""Current host permission, cursor and queue ledger projections. No object grants an actual run lease."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from mingjing_core.memory2.contracts import MemoryScope

from .validation import ReflectionError, booleans, instant, integer, opaque, sha, typed_tuple


@dataclass(frozen=True)
class BackgroundPermit:
    scope: MemoryScope
    revision: int
    current_revision: int
    enabled: bool = False
    quota_stopped: bool = True
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise ReflectionError("permit_scope_required")
        integer(self.revision)
        integer(self.current_revision)
        booleans(self.enabled, self.quota_stopped, self.active)


@dataclass(frozen=True)
class ProcessedSource:
    id: str
    revision: int
    content_sha256: str

    def __post_init__(self) -> None:
        opaque(self.id)
        integer(self.revision, 1)
        sha(self.content_sha256)


@dataclass(frozen=True)
class ThreadState:
    scope: MemoryScope
    id: str
    revision: int
    last_activity_at: datetime
    source_ids: tuple[str, ...]
    processed_sources: tuple[ProcessedSource, ...] = ()
    processed_epoch: int | None = None
    last_observed_at: datetime | None = None
    daily_completed_on: date | None = None
    incognito: bool = False
    active: bool = True
    retention_scope: str = "persistent"
    running: bool = False
    lease_until: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise ReflectionError("thread_scope_required")
        opaque(self.id)
        integer(self.revision)
        booleans(self.incognito, self.active, self.running)
        object.__setattr__(self, "source_ids", typed_tuple(self.source_ids, str))
        opaque(*self.source_ids)
        object.__setattr__(self, "processed_sources", typed_tuple(self.processed_sources, ProcessedSource))
        if len(set(self.source_ids)) != len(self.source_ids) or len({row.id for row in self.processed_sources}) != len(
            self.processed_sources
        ):
            raise ReflectionError("duplicate_thread_source")
        if self.processed_epoch is not None:
            integer(self.processed_epoch)
        for name in ("last_activity_at", "last_observed_at", "lease_until"):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, instant(getattr(self, name)))
        if self.daily_completed_on is not None and type(self.daily_completed_on) is not date:
            raise ReflectionError("daily_completion_date_invalid")
        if type(self.retention_scope) is not str or self.retention_scope not in {"persistent", "temporary"}:
            raise ReflectionError("thread_retention_invalid")


@dataclass(frozen=True)
class ReflectionOperation:
    scope: MemoryScope
    thread_id: str
    operation_id: str
    input_fingerprint: str
    state: str = "queued"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise ReflectionError("operation_scope_required")
        opaque(self.thread_id, self.operation_id)
        sha(self.input_fingerprint)
        if type(self.state) is not str or self.state not in {"queued", "running", "completed", "cancelled"}:
            raise ReflectionError("operation_state_invalid")


@dataclass(frozen=True)
class ReflectionIntent:
    scope: MemoryScope
    thread_id: str
    operation_id: str
    input_fingerprint: str
    trigger: str
    not_before: datetime
    snapshot_revision: int
    source_epoch: int
    thread_revision: int
    permit_revision: int
    source_manifest: tuple[ProcessedSource, ...]
    kind: str = "reflection"
    lane: str = "background"
    timezone: str = "Asia/Shanghai"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise ReflectionError("intent_scope_required")
        opaque(self.thread_id, self.operation_id)
        sha(self.input_fingerprint)
        if (
            type(self.trigger) is not str
            or self.trigger not in {"idle", "daily"}
            or self.kind != "reflection"
            or self.lane != "background"
        ):
            raise ReflectionError("intent_kind_invalid")
        object.__setattr__(self, "not_before", instant(self.not_before))
        for value in (self.snapshot_revision, self.source_epoch, self.thread_revision, self.permit_revision):
            integer(value)
        object.__setattr__(self, "source_manifest", typed_tuple(self.source_manifest, ProcessedSource))
        if len({row.id for row in self.source_manifest}) != len(self.source_manifest):
            raise ReflectionError("duplicate_intent_source")
        try:
            ZoneInfo(self.timezone)
        except (TypeError, ValueError, KeyError):
            raise ReflectionError("timezone_invalid") from None


@dataclass(frozen=True)
class ScheduleDecision:
    disposition: str
    reason: str
    intent: ReflectionIntent | None = None
    replayed: bool = False

    def __post_init__(self) -> None:
        if type(self.disposition) is not str or self.disposition not in {"enqueue", "noop", "blocked"}:
            raise ReflectionError("schedule_disposition_invalid")
        booleans(self.replayed)
        if (self.disposition == "enqueue") != (self.intent is not None):
            raise ReflectionError("schedule_intent_mismatch")

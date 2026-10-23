"""Retention emits a compare-and-check plan, never a database deletion."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from mingjing_core.timekit.clock import Clock

from .event_models import RunScope
from .store_contracts import StoredEventMetadata as StoreMetadata
from .stream_clock import StreamStateError, observe, utc


@dataclass(frozen=True)
class CommittedRun:
    scope: RunScope
    committed_at: datetime
    final_seq: int
    message_id: str
    revision: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "committed_at", utc(self.committed_at))
        if not isinstance(self.scope, RunScope) or not isinstance(self.message_id, str) or not self.message_id:
            raise StreamStateError("运行提交证明无效")
        if type(self.final_seq) is not int or self.final_seq < 1 or type(self.revision) is not int or self.revision < 1:
            raise StreamStateError("运行提交版本无效")


@dataclass(frozen=True)
class StoredEventMetadata:
    scope: RunScope
    seq: int
    type: str
    created_at: datetime
    payload_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", utc(self.created_at))
        if not isinstance(self.scope, RunScope) or type(self.seq) is not int or self.seq < 1:
            raise StreamStateError("清理事件范围或序号无效")
        if not isinstance(self.type, str) or not self.type:
            raise StreamStateError("清理事件类型无效")
        if not isinstance(self.payload_fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", self.payload_fingerprint):
            raise StreamStateError("清理事件指纹无效")


@dataclass(frozen=True)
class CleanupPlan:
    scope: RunScope
    operation_id: str
    eligible_refs: tuple[StoredEventMetadata, ...]
    due_after: datetime
    expected_commit_revision: int
    final_seq: int
    message_id: str
    ready: bool
    reason: str


def metadata_for_cleanup(row: StoreMetadata | StoredEventMetadata) -> StoredEventMetadata:
    if isinstance(row, StoredEventMetadata):
        return row
    if not isinstance(row, StoreMetadata):
        raise StreamStateError("清理需要存储端的元数据投影")
    return StoredEventMetadata(row.scope, row.seq, row.type, row.created_at, row.fingerprint)


def plan_delta_cleanup(
    committed: CommittedRun, rows: tuple[StoredEventMetadata | StoreMetadata, ...], *, clock: Clock
) -> CleanupPlan:
    rows = tuple(metadata_for_cleanup(row) for row in rows)
    stamp = observe(clock, None)
    due = committed.committed_at + timedelta(hours=24)
    if len({row.seq for row in rows}) != len(rows):
        raise StreamStateError("清理快照含重复序号")
    for row in rows:
        if row.scope != committed.scope:
            raise StreamStateError("清理快照混入其他运行")
        if row.seq <= committed.final_seq and row.created_at > committed.committed_at:
            raise StreamStateError("清理快照与提交证明不一致")
    eligible = tuple(
        sorted(
            (row for row in rows if row.type == "text_delta" and row.seq <= committed.final_seq and stamp >= due),
            key=lambda row: row.seq,
        )
    )
    identity = repr((committed, [(row.seq, row.payload_fingerprint) for row in eligible]))
    operation = "delta-cleanup:" + hashlib.sha256(identity.encode()).hexdigest()
    return CleanupPlan(
        committed.scope,
        operation,
        eligible,
        due,
        committed.revision,
        committed.final_seq,
        committed.message_id,
        stamp >= due,
        "eligible" if stamp >= due else "not_due",
    )

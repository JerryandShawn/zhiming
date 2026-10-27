"""Explicit synthetic migration projections; none is a database write capability."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from mingjing_core.memory2.contracts import MemoryScope, MemorySource, SourceAnchor
from mingjing_core.memory2.validation import frozen_tuple, require_bool, require_int, require_text, unique
from mingjing_core.organize.changes import ChangeSet, FieldChange
from mingjing_core.organize.supplement_v2.contracts import labels
from mingjing_core.streaming.json_values import freeze_json, json_object


class DryRunError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__("离线整理候选不可用，请核对来源与版本后重试")


def fingerprint_value(value: object) -> None:
    import re

    if type(value) is not str or re.fullmatch("[a-f0-9]{64}", value) is None:
        raise DryRunError("fingerprint_invalid")


def identifier(value: object) -> str:
    import re

    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", value) is None:
        raise DryRunError("opaque_identifier_required")
    return value


@dataclass(frozen=True)
class DryRunLedger:
    operation_id: str
    input_fingerprint: str
    plan_fingerprint: str
    state: str = "planned"
    applied_revision: int | None = None
    target_revisions: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        identifier(self.operation_id)
        fingerprint_value(self.input_fingerprint)
        fingerprint_value(self.plan_fingerprint)
        if self.state not in {"planned", "applied", "undone"}:
            raise DryRunError("ledger_state_invalid")
        if self.state == "applied":
            require_int(self.applied_revision, 1)
        elif self.applied_revision is not None:
            raise DryRunError("ledger_revision_invalid")
        values = frozen_tuple(self.target_revisions, tuple)
        for entry in values:
            if len(entry) != 2:
                raise DryRunError("ledger_target_revision_invalid")
            require_text(entry[0])
            require_int(entry[1], 1)
        unique(entry[0] for entry in values)
        if self.state != "applied" and values:
            raise DryRunError("ledger_target_revision_invalid")
        object.__setattr__(self, "target_revisions", values)


@dataclass(frozen=True)
class ExportSnapshot:
    """Host-supplied current scope/row/source ledger, not self-authenticating JSON."""

    scope: MemoryScope
    revision: int
    source_epoch: int
    document: Mapping[str, Any] = field(repr=False)
    sources: tuple[MemorySource, ...] = field(repr=False)
    operations: tuple[DryRunLedger, ...] = ()
    synthetic: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MemoryScope):
            raise DryRunError("scope_required")
        require_int(self.revision)
        require_int(self.source_epoch)
        require_bool(self.synthetic)
        if not self.synthetic:
            raise DryRunError("synthetic_only")
        object.__setattr__(self, "document", freeze_json(json_object(self.document)))
        object.__setattr__(self, "sources", frozen_tuple(self.sources, MemorySource))
        object.__setattr__(self, "operations", frozen_tuple(self.operations, DryRunLedger))
        unique(item.id for item in self.sources)
        unique(item.operation_id for item in self.operations)


@dataclass(frozen=True)
class ExportMessage:
    id: str
    scope: MemoryScope
    revision: int
    role: str
    text: str = field(repr=False)
    at_ms: int
    thread_id: str
    anchor: SourceAnchor = field(repr=False)
    current_labels: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        identifier(self.id)
        identifier(self.thread_id)
        require_text(self.text)
        require_int(self.revision, 1)
        require_int(self.at_ms)
        if not isinstance(self.scope, MemoryScope) or not isinstance(self.anchor, SourceAnchor):
            raise DryRunError("message_scope_or_anchor_invalid")
        if self.role not in {"user", "assistant"}:
            raise DryRunError("message_role_invalid")
        # A legacy null confidence is a before-value, never a valid newly proposed confidence.
        labels(
            {key: value for key, value in self.current_labels.items() if key != "route_confidence" or value is not None}
        )
        object.__setattr__(self, "current_labels", MappingProxyType(dict(self.current_labels)))


@dataclass(frozen=True)
class DryRunConflict:
    entity_id: str
    reason_code: str


@dataclass(frozen=True)
class ParsedExport:
    export_id: str
    input_fingerprint: str
    payload: Mapping[str, Any] = field(repr=False)
    messages: tuple[ExportMessage, ...] = field(repr=False)
    conflicts: tuple[DryRunConflict, ...] = ()


@dataclass(frozen=True)
class TopicCandidate:
    id: str
    space_id: str
    title: str = field(repr=False)
    message_ids: tuple[str, ...]
    start_ms: int
    end_ms: int
    sample: str = field(repr=False)


@dataclass(frozen=True)
class MessagePrecondition:
    id: str
    revision: int
    source_id: str
    source_revision: int
    immutable_fingerprint: str


@dataclass(frozen=True)
class DryRunPlan:
    scope: MemoryScope
    operation_id: str
    export_id: str
    input_fingerprint: str
    expected_revision: int
    source_epoch: int
    change_set: ChangeSet = field(repr=False)
    topics: tuple[TopicCandidate, ...] = field(repr=False)
    waiting_ids: tuple[str, ...]
    conflicts: tuple[DryRunConflict, ...]
    preconditions: tuple[MessagePrecondition, ...]
    anchors: tuple[SourceAnchor, ...] = field(repr=False)
    original_payload: Mapping[str, Any] = field(repr=False)
    fingerprint: str
    replayed: bool = False

    @property
    def requires_user_review(self) -> bool:
        return True


@dataclass(frozen=True)
class UndoPreview:
    operation_id: str
    plan_fingerprint: str
    inverse_ops: tuple[FieldChange, ...] = field(repr=False)
    conflicts: tuple[DryRunConflict, ...] = ()
    already_undone: bool = False

    @property
    def allowed(self) -> bool:
        return not self.conflicts and not self.already_undone

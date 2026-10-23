"""Metadata-only, immutable intent projections; authoritative storage must fence every transition."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime


class StreamError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__("流式投递状态无效，须核对后继续")


def identity(value: object) -> None:
    if type(value) is not str or not value.strip() or len(value) > 300 or any(ord(char) < 32 for char in value):
        raise StreamError("identity_invalid")


def digest(value: object) -> None:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise StreamError("fingerprint_invalid")


def integer(value: object, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise StreamError("integer_invalid")


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise StreamError("aware_time_required")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class StreamScope:
    owner_id: str
    subject_id: str
    outbox_id: str
    run_id: str
    business_id: str
    channel: str
    target: str = field(repr=False)  # 待对照飞书官方文档核实。

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            identity(getattr(self, name))


@dataclass(frozen=True)
class StreamIntent:
    operation_id: str
    kind: str
    payload_fingerprint: str
    sequence: int | None = None  # 待对照飞书官方文档核实。

    def __post_init__(self) -> None:
        identity(self.operation_id)
        digest(self.payload_fingerprint)
        if type(self.kind) is not str or self.kind not in {"create", "send", "update", "close", "fallback"}:
            raise StreamError("operation_kind_invalid")
        if self.kind in {"update", "close"}:
            integer(self.sequence, 1)
        elif self.sequence is not None:
            raise StreamError("unsequenced_operation_required")


@dataclass(frozen=True)
class StreamLease:
    token_hash: str = field(repr=False)
    worker_id: str
    fence: int
    expires_at: datetime

    def __post_init__(self) -> None:
        digest(self.token_hash)
        identity(self.worker_id)
        integer(self.fence, 1)
        object.__setattr__(self, "expires_at", utc(self.expires_at))


@dataclass(frozen=True)
class IntentRecord:
    intent: StreamIntent
    status: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.intent, StreamIntent)
            or type(self.status) is not str
            or self.status not in {"acked", "rejected"}
        ):
            raise StreamError("history_record_invalid")


@dataclass(frozen=True)
class StreamState:
    scope: StreamScope
    intent: StreamIntent
    phase: str = "prepared"
    revision: int = 0
    fence: int = 0
    lease: StreamLease | None = None
    card_id: str | None = None  # 待对照飞书官方文档核实。
    message_id: str | None = None  # 待对照飞书官方文档核实。
    last_reserved_sequence: int = 0
    last_acked_sequence: int = 0
    attempts: int = 0
    history: tuple[IntentRecord, ...] = ()
    evidence_ref: str | None = None
    dispatch_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, StreamScope) or not isinstance(self.intent, StreamIntent):
            raise StreamError("state_binding_invalid")
        if type(self.phase) is not str or self.phase not in {
            "prepared",
            "leased",
            "dispatched",
            "acked",
            "rejected",
            "uncertain",
        }:
            raise StreamError("state_phase_invalid")
        for name in ("revision", "fence", "last_reserved_sequence", "last_acked_sequence", "attempts"):
            integer(getattr(self, name))
        if self.last_acked_sequence > self.last_reserved_sequence:
            raise StreamError("sequence_order_invalid")
        for value in (self.card_id, self.message_id, self.evidence_ref):
            if value is not None:
                identity(value)
        if self.lease is not None and (not isinstance(self.lease, StreamLease) or self.lease.fence != self.fence):
            raise StreamError("lease_fence_invalid")
        if self.phase in {"leased", "dispatched"} and self.lease is None:
            raise StreamError("lease_required")
        if self.phase not in {"leased", "dispatched"} and self.lease is not None:
            raise StreamError("unexpected_lease")
        if not isinstance(self.history, (list, tuple)) or any(
            not isinstance(item, IntentRecord) for item in self.history
        ):
            raise StreamError("history_invalid")
        object.__setattr__(self, "history", tuple(self.history))
        if len({record.intent.operation_id for record in self.history}) != len(self.history):
            raise StreamError("history_operation_duplicate")
        if any(item.intent.operation_id == self.intent.operation_id for item in self.history):
            raise StreamError("current_operation_in_history")
        _history_sequences(self)
        if self.dispatch_fingerprint is not None:
            digest(self.dispatch_fingerprint)
        _state_shape(self)


def _history_sequences(state: StreamState) -> None:
    # Checkpoint bootstrap can retain a suffix: order and bounds matter, not a complete or contiguous history.
    previous = 0
    for record in state.history:
        sequence = record.intent.sequence
        if sequence is None:
            continue
        if state.intent.sequence is None or not previous < sequence < state.intent.sequence:
            raise StreamError("history_sequence_invalid")
        if record.status == "acked" and sequence > state.last_acked_sequence:
            raise StreamError("history_acked_sequence_invalid")
        previous = sequence


def _state_shape(state: StreamState) -> None:
    intent = state.intent
    if intent.kind == "fallback":
        raise StreamError("fallback_is_separate_outbox_intent")
    if intent.kind == "create":
        if (state.card_id is not None) != (state.phase == "acked") or state.message_id is not None:
            raise StreamError("created_state_identity_invalid")
    elif intent.kind == "send":
        if state.card_id is None or (state.message_id is not None) != (state.phase == "acked"):
            raise StreamError("sent_state_identity_invalid")
    elif state.card_id is None or state.message_id is None or intent.sequence != state.last_reserved_sequence:
        raise StreamError("streaming_state_identity_invalid")
    if intent.sequence is None and (state.last_reserved_sequence or state.last_acked_sequence):
        raise StreamError("unsequenced_state_has_sequence")
    if state.phase in {"prepared", "leased"}:
        if state.dispatch_fingerprint is not None:
            raise StreamError("undispatched_state_has_dispatch_evidence")
    elif state.dispatch_fingerprint is None or not state.attempts or not state.fence:
        raise StreamError("dispatch_evidence_missing")
    if intent.sequence is not None:
        if state.phase == "acked" and state.last_acked_sequence != intent.sequence:
            raise StreamError("acked_sequence_invalid")
        if state.phase != "acked" and state.last_acked_sequence >= intent.sequence:
            raise StreamError("reserved_sequence_already_acked")


@dataclass(frozen=True)
class LeaseGrant:
    state: StreamState
    token: str = field(repr=False)


@dataclass(frozen=True)
class StreamReceipt:
    scope: StreamScope
    operation_id: str
    payload_fingerprint: str
    sequence: int | None = None
    card_id: str | None = None  # 待对照飞书官方文档核实。
    message_id: str | None = None  # 待对照飞书官方文档核实。
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, StreamScope):
            raise StreamError("receipt_scope_invalid")
        identity(self.operation_id)
        digest(self.payload_fingerprint)
        if self.sequence is not None:
            integer(self.sequence, 1)
        for value in (self.card_id, self.message_id, self.evidence_ref):
            if value is not None:
                identity(value)

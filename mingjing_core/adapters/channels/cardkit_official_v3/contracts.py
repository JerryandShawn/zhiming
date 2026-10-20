"""Immutable offline protocol projections; host transactions remain the authority."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mingjing_core.adapters.channels.card_limits_official_v3 import validate_card_id, validate_sequence, wire_uuid
from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import StreamScope, StreamState
from mingjing_core.adapters.channels.stream_outbox_v2.contracts import digest, identity, integer, utc
from mingjing_core.streaming.json_values import freeze_json, json_object


class OfficialError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__("卡片协议状态不可用，须核对后继续")


@dataclass(frozen=True)
class OfficialPolicy:
    interval_ms: int = 400
    allow_sequence_gaps: bool = True  # 官方未说明，stage 实测项（26 §2.4）。

    def __post_init__(self) -> None:
        if type(self.interval_ms) is not int or not 300 <= self.interval_ms <= 500:
            raise OfficialError("interval_invalid")
        if type(self.allow_sequence_gaps) is not bool:
            raise OfficialError("sequence_gap_policy_invalid")


@dataclass(frozen=True)
class ArtifactEvidence:
    """Current host-approved rendered artifact, not a self-authenticating database receipt."""

    scope: StreamScope
    run_payload_fingerprint: str
    revision: int
    final_card: Mapping[str, Any] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.scope, StreamScope):
            raise OfficialError("artifact_scope_invalid")
        digest(self.run_payload_fingerprint)
        integer(self.revision, 1)
        object.__setattr__(self, "final_card", freeze_json(json_object(self.final_card)))

    @property
    def fingerprint(self) -> str:
        from mingjing_core.streaming.json_values import thaw_json

        return fingerprint([self.run_payload_fingerprint, self.revision, thaw_json(self.final_card)])


@dataclass(frozen=True)
class OfficialRequest:
    kind: str
    method: str
    path: str
    query: Mapping[str, Any]
    body: Mapping[str, Any] = field(repr=False)
    operation_id: str
    wire_uuid: str
    sequence: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in {"create", "send", "update", "finalize", "close_streaming"}:
            raise OfficialError("wire_kind_invalid")
        identity(self.operation_id)
        if self.wire_uuid != wire_uuid(self.operation_id):
            raise OfficialError("wire_uuid_mismatch")
        if type(self.method) is not str or self.method not in {"POST", "PUT", "PATCH"}:
            raise OfficialError("wire_method_invalid")
        if type(self.path) is not str or not self.path.startswith("/open-apis/"):
            raise OfficialError("wire_path_invalid")
        if self.kind in {"update", "finalize", "close_streaming"}:
            validate_sequence(self.sequence)
        elif self.sequence is not None:
            raise OfficialError("unsequenced_operation_required")
        for key in ("query", "body"):
            object.__setattr__(self, key, freeze_json(json_object(getattr(self, key))))

    @property
    def fingerprint(self) -> str:
        from mingjing_core.streaming.json_values import thaw_json

        return fingerprint([self.kind, self.method, self.path, thaw_json(self.query), thaw_json(self.body)])

    @property
    def content_fingerprint(self) -> str:
        from mingjing_core.streaming.json_values import thaw_json

        body = thaw_json(self.body)
        return fingerprint(
            [self.kind, self.method, self.path, {k: v for k, v in body.items() if k not in {"uuid", "sequence"}}]
        )


@dataclass(frozen=True)
class OfficialOperation:
    kind: str
    operation_id: str
    wire_uuid: str
    payload_fingerprint: str
    sequence: int | None
    content_fingerprint: str

    def __post_init__(self) -> None:
        identity(self.operation_id)
        digest(self.payload_fingerprint)
        digest(self.content_fingerprint)
        if type(self.kind) is not str or self.kind not in {"create", "send", "update", "finalize", "close_streaming"}:
            raise OfficialError("operation_kind_invalid")
        if self.wire_uuid != wire_uuid(self.operation_id):
            raise OfficialError("wire_uuid_mismatch")
        if self.kind in {"update", "finalize", "close_streaming"}:
            validate_sequence(self.sequence)
        elif self.sequence is not None:
            raise OfficialError("unsequenced_operation_required")


@dataclass(frozen=True)
class OfficialState:
    scope: StreamScope
    policy: OfficialPolicy = OfficialPolicy()
    stage: str = "new"
    revision: int = 0
    lease_state: StreamState | None = None
    operation: OfficialOperation | None = None
    artifact_fingerprint: str | None = None
    card_id: str | None = None
    message_id: str | None = None
    last_reserved_sequence: int = 0
    last_acked_sequence: int = 0
    last_attempt_at: datetime | None = None
    started_at: datetime | None = None
    not_before: datetime | None = None
    finalize_acked: bool = False
    close_acked: bool = False
    close_retries: int = 0
    retry_kind: str | None = None
    retry_reason: str | None = None
    history: tuple[OfficialOperation, ...] = ()

    def __post_init__(self) -> None:
        from .validation import validate_state

        validate_state(self)

    @property
    def phase(self) -> str:
        if self.lease_state is not None and self.lease_state.phase in {"leased", "dispatched", "uncertain"}:
            return self.lease_state.phase
        return self.stage


@dataclass(frozen=True)
class PreparedOperation:
    state: OfficialState
    request: OfficialRequest | None = field(default=None, repr=False)
    status: str = "prepared"


@dataclass(frozen=True)
class OfficialOutcome:
    status: str
    reason: str
    after_ms: int = 0
    action_required: str | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not str or self.status not in {"retryable", "rejected", "uncertain"}:
            raise OfficialError("outcome_status_invalid")
        integer(self.after_ms)
        identity(self.reason)
        if self.action_required is not None and self.action_required != "reopen_or_finalize":
            raise OfficialError("host_action_invalid")
        if self.status != "retryable" and (self.after_ms or self.action_required is not None):
            raise OfficialError("non_retryable_has_retry_fields")


@dataclass(frozen=True)
class OfficialAck:
    card_id: str | None = None
    message_id: str | None = None
    sequence: int | None = None

    def __post_init__(self) -> None:
        if self.card_id is not None:
            validate_card_id(self.card_id)
        if self.message_id is not None:
            identity(self.message_id)
        if self.sequence is not None:
            validate_sequence(self.sequence)


@dataclass(frozen=True)
class OfficialFallback:
    operation_id: str
    card_id: str
    message_id: str
    artifact_fingerprint: str
    reason: str = "finalize_rejected"

    def __post_init__(self) -> None:
        identity(self.operation_id)
        validate_card_id(self.card_id)
        identity(self.message_id)
        digest(self.artifact_fingerprint)
        if self.reason != "finalize_rejected":
            raise OfficialError("fallback_reason_invalid")


def now_utc(value: datetime) -> datetime:
    return utc(value)

"""Offline CardKit candidates. Wire names are provisional; no HTTP or SDK is imported."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

OperationKind = Literal["create", "send", "update", "close"]
CardPhase = Literal["new", "created", "streaming", "in_flight", "uncertain", "closed", "fallback_pending"]


class CardKitStateError(ValueError):
    """A safe state code, never external response bodies or card text."""


class CardKitRejected(RuntimeError):
    """Only an explicitly confirmed remote refusal; arbitrary transport errors are uncertain."""


def identifier(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 300 or any(ord(char) < 32 for char in value):
        raise CardKitStateError("invalid_cardkit_identifier")
    return value


def canonical(value: Any) -> str:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise CardKitStateError("invalid_cardkit_json_keys")
        for child in value.values():
            canonical(child)
    elif isinstance(value, list):
        for child in value:
            canonical(child)
    elif value is not None and type(value) not in {str, bool, int, float}:
        raise CardKitStateError("invalid_cardkit_json_value")
    elif isinstance(value, float) and not math.isfinite(value):
        raise CardKitStateError("invalid_cardkit_json_number")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: Any) -> str:
    try:
        return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise CardKitStateError("invalid_cardkit_fingerprint_input") from None


@dataclass(frozen=True)
class CardScope:
    owner_id: str
    subject_id: str
    open_id: str = field(repr=False)  # 待对照飞书官方文档核实。
    business_id: str

    def __post_init__(self) -> None:
        for value in (self.owner_id, self.subject_id, self.open_id, self.business_id):
            identifier(value)

    @property
    def key(self) -> str:
        # Target is fixed by the first scoped record; changing it cannot create a second delivery key.
        return fingerprint([self.owner_id, self.subject_id, self.business_id])


@dataclass(frozen=True)
class CardKitAck:
    card_id: str | None = None  # 待对照飞书官方文档核实。
    message_id: str | None = None  # 待对照飞书官方文档核实。
    sequence: int | None = None  # 待对照飞书官方文档核实。

    def __post_init__(self) -> None:
        for value in (self.card_id, self.message_id):
            if value is not None:
                identifier(value)
        if self.sequence is not None and (type(self.sequence) is not int or self.sequence < 1):
            raise CardKitStateError("invalid_cardkit_ack_sequence")


class CardKitTransport(Protocol):
    def create(self, card: Mapping[str, Any], *, operation_id: str) -> CardKitAck:
        """card/operation_id and create mapping: 待对照飞书官方文档核实。"""
        ...

    def send(self, card_id: str, open_id: str, *, operation_id: str) -> CardKitAck:
        """card_id/open_id/operation_id and send mapping: 待对照飞书官方文档核实。"""
        ...

    def update(self, card_id: str, element_id: str, text: str, *, sequence: int, operation_id: str) -> CardKitAck:
        """All external identifiers, text and sequence mapping: 待对照飞书官方文档核实。"""
        ...

    def close(self, card_id: str, final_card: Mapping[str, Any], *, sequence: int, operation_id: str) -> CardKitAck:
        """Final layout/streaming disable API and sequence: 待对照飞书官方文档核实。"""
        ...


@dataclass(frozen=True)
class PendingOperation:
    kind: OperationKind
    operation_id: str
    fingerprint: str
    sequence: int | None
    reserved_at_ms: int


@dataclass(frozen=True)
class CardCheckpoint:
    scope: CardScope
    phase: CardPhase = "new"
    version: int = 0
    card_id: str | None = None
    message_id: str | None = None
    last_reserved_sequence: int = 0
    last_acked_sequence: int = 0
    last_attempt_ms: int | None = None
    pending: PendingOperation | None = None
    initial_fingerprint: str | None = None
    last_text_fingerprint: str | None = None
    final_fingerprint: str | None = None
    evidence_ref: str | None = None


@dataclass(frozen=True)
class FallbackIntent:
    operation_id: str
    card_id: str
    message_id: str
    final_fingerprint: str
    reason: Literal["close_rejected"] = "close_rejected"


@dataclass(frozen=True)
class CardKitResult:
    status: str
    checkpoint: CardCheckpoint
    next_due_ms: int | None = None
    fallback_intent: FallbackIntent | None = None

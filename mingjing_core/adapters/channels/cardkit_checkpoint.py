"""Metadata-only checkpoints for offline tests; snapshots are neither durable nor authenticated leases."""

from __future__ import annotations

import re
from dataclasses import asdict, fields, replace
from typing import Any

from .cardkit_contracts import CardCheckpoint, CardKitStateError, CardScope, PendingOperation, identifier


def valid_fingerprint(value: object, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise CardKitStateError("invalid_checkpoint_fingerprint")


def _integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise CardKitStateError("invalid_checkpoint_integer")
    return value


def snapshot(checkpoint: CardCheckpoint) -> dict[str, Any]:
    return {"schema": "cardkit-offline-v1", "durable": False, "checkpoint": asdict(checkpoint)}


def _pending(value: object, reserved: int) -> PendingOperation | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(PendingOperation)}:
        raise CardKitStateError("invalid_checkpoint_pending_shape")
    pending = PendingOperation(**value)
    if pending.kind not in {"create", "send", "update", "close"}:
        raise CardKitStateError("invalid_checkpoint_operation")
    identifier(pending.operation_id)
    valid_fingerprint(pending.fingerprint)
    _integer(pending.reserved_at_ms)
    if pending.kind in {"update", "close"}:
        if type(pending.sequence) is not int or pending.sequence < 1 or pending.sequence != reserved:
            raise CardKitStateError("invalid_checkpoint_pending_sequence")
    elif pending.sequence is not None:
        raise CardKitStateError("invalid_checkpoint_unsequenced_operation")
    return pending


def _validate_phase(checkpoint: CardCheckpoint) -> None:
    phase, pending = checkpoint.phase, checkpoint.pending
    if phase not in {"new", "created", "streaming", "in_flight", "uncertain", "closed", "fallback_pending"}:
        raise CardKitStateError("invalid_checkpoint_phase")
    if (phase in {"in_flight", "uncertain"}) != (pending is not None):
        raise CardKitStateError("invalid_checkpoint_pending_phase")
    known_card = phase in {"created", "streaming", "closed", "fallback_pending"} or (
        pending is not None and pending.kind != "create"
    )
    known_message = phase in {"streaming", "closed", "fallback_pending"} or (
        pending is not None and pending.kind in {"update", "close"}
    )
    if known_card != (checkpoint.card_id is not None) or known_message != (checkpoint.message_id is not None):
        raise CardKitStateError("invalid_checkpoint_remote_identity")
    if phase != "new" and checkpoint.initial_fingerprint is None:
        raise CardKitStateError("missing_checkpoint_initial_fingerprint")
    if phase in {"closed", "fallback_pending"} and checkpoint.final_fingerprint is None:
        raise CardKitStateError("missing_checkpoint_final_fingerprint")
    if phase == "closed" and not 0 < checkpoint.last_acked_sequence == checkpoint.last_reserved_sequence:
        raise CardKitStateError("invalid_checkpoint_closed_sequence")


def restore_snapshot(value: dict[str, Any], *, scope: CardScope) -> CardCheckpoint:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "durable", "checkpoint"}
        or value["schema"] != "cardkit-offline-v1"
        or value["durable"] is not False
    ):
        raise CardKitStateError("invalid_checkpoint_schema")
    data = value["checkpoint"]
    if not isinstance(data, dict) or set(data) != {item.name for item in fields(CardCheckpoint)}:
        raise CardKitStateError("invalid_checkpoint_shape")
    if data["scope"] != asdict(scope):
        raise CardKitStateError("checkpoint_scope_mismatch")
    for name in ("version", "last_reserved_sequence", "last_acked_sequence"):
        _integer(data[name])
    if data["last_acked_sequence"] > data["last_reserved_sequence"]:
        raise CardKitStateError("invalid_checkpoint_sequence_order")
    if data["last_attempt_ms"] is not None:
        _integer(data["last_attempt_ms"])
    for name in ("initial_fingerprint", "last_text_fingerprint", "final_fingerprint"):
        valid_fingerprint(data[name], optional=True)
    for name in ("card_id", "message_id", "evidence_ref"):
        if data[name] is not None:
            identifier(data[name])
    pending = _pending(data["pending"], data["last_reserved_sequence"])
    checkpoint = CardCheckpoint(**dict(data, scope=scope, pending=pending))
    _validate_phase(checkpoint)
    if pending is not None:
        # A reserved operation may already have escaped the old process; never infer that it was unsent.
        checkpoint = replace(checkpoint, phase="uncertain", version=checkpoint.version + 1)
    return checkpoint

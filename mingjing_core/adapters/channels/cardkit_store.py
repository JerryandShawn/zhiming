"""Atomic in-memory reservations for injected transports; production requires a durable fenced adapter."""

from __future__ import annotations

from dataclasses import replace
from threading import RLock
from typing import Any

from .cardkit_checkpoint import restore_snapshot, snapshot, valid_fingerprint
from .cardkit_contracts import (
    CardCheckpoint,
    CardKitAck,
    CardKitStateError,
    CardScope,
    OperationKind,
    PendingOperation,
    fingerprint,
    identifier,
)


class MemoryCardKitStore:
    """Same-instance concurrency only. Restoring a snapshot does not fence a live old process."""

    durable = False

    def __init__(self) -> None:
        self._lock = RLock()
        self._checkpoints: dict[str, CardCheckpoint] = {}

    def get(self, scope: CardScope) -> CardCheckpoint:
        with self._lock:
            current = self._checkpoints.setdefault(scope.key, CardCheckpoint(scope))
            if current.scope != scope:
                raise CardKitStateError("cardkit_business_target_changed")
            return current

    def snapshot(self, scope: CardScope) -> dict[str, Any]:
        with self._lock:
            return snapshot(self.get(scope))

    @classmethod
    def from_snapshot(cls, value: dict[str, Any], *, scope: CardScope) -> MemoryCardKitStore:
        checkpoint = restore_snapshot(value, scope=scope)
        store = cls()
        store._checkpoints[scope.key] = checkpoint
        return store

    def reserve(
        self,
        scope: CardScope,
        *,
        expected_version: int,
        kind: OperationKind,
        payload_fingerprint: str,
        now_ms: int,
        interval_ms: int,
    ) -> CardCheckpoint:
        with self._lock:
            current = self.get(scope)
            if current.version != expected_version or current.pending is not None:
                raise CardKitStateError("cardkit_reservation_conflict")
            valid_fingerprint(payload_fingerprint)
            if type(now_ms) is not int or now_ms < 0 or type(interval_ms) is not int or not 300 <= interval_ms <= 500:
                raise CardKitStateError("invalid_cardkit_reservation_clock")
            self._check_reservation(current, kind, payload_fingerprint, now_ms, interval_ms)
            sequence = current.last_reserved_sequence + 1 if kind in {"update", "close"} else None
            operation_id = "cardkit:" + fingerprint([scope.key, kind, sequence, payload_fingerprint])
            pending = PendingOperation(kind, operation_id, payload_fingerprint, sequence, now_ms)
            checkpoint = replace(
                current,
                phase="in_flight",
                version=current.version + 1,
                pending=pending,
                last_attempt_ms=now_ms,
                last_reserved_sequence=sequence if sequence is not None else current.last_reserved_sequence,
                initial_fingerprint=payload_fingerprint if kind == "create" else current.initial_fingerprint,
                final_fingerprint=payload_fingerprint if kind == "close" else current.final_fingerprint,
            )
            self._checkpoints[scope.key] = checkpoint
            return checkpoint

    @staticmethod
    def _check_reservation(
        current: CardCheckpoint, kind: OperationKind, digest: str, now_ms: int, interval_ms: int
    ) -> None:
        phases = {"create": "new", "send": "created", "update": "streaming", "close": "streaming"}
        if kind not in phases or current.phase != phases[kind]:
            raise CardKitStateError("cardkit_operation_not_allowed")
        if current.last_attempt_ms is not None and now_ms < current.last_attempt_ms:
            raise CardKitStateError("cardkit_clock_went_backwards")
        if (
            kind in {"update", "close"}
            and current.last_attempt_ms is not None
            and now_ms - current.last_attempt_ms < interval_ms
        ):
            raise CardKitStateError("cardkit_throttled")
        if kind == "create" and current.initial_fingerprint not in {None, digest}:
            raise CardKitStateError("cardkit_initial_payload_changed")
        if kind == "close" and current.final_fingerprint not in {None, digest}:
            raise CardKitStateError("cardkit_final_payload_changed")

    def _pending(self, scope: CardScope, operation_id: str) -> tuple[CardCheckpoint, PendingOperation]:
        checkpoint = self.get(scope)
        pending = checkpoint.pending
        if pending is None or pending.operation_id != operation_id:
            raise CardKitStateError("cardkit_pending_operation_mismatch")
        return checkpoint, pending

    def confirm(self, scope: CardScope, operation_id: str, ack: CardKitAck) -> CardCheckpoint:
        with self._lock:
            current, pending = self._pending(scope, operation_id)
            self._check_ack(current, pending, ack)
            kind = pending.kind
            checkpoint = replace(
                current,
                version=current.version + 1,
                pending=None,
                phase="created" if kind == "create" else "closed" if kind == "close" else "streaming",
                card_id=ack.card_id if kind == "create" else current.card_id,
                message_id=ack.message_id if kind == "send" else current.message_id,
                last_acked_sequence=pending.sequence if pending.sequence is not None else current.last_acked_sequence,
                last_text_fingerprint=pending.fingerprint if kind == "update" else current.last_text_fingerprint,
            )
            self._checkpoints[scope.key] = checkpoint
            return checkpoint

    @staticmethod
    def _check_ack(current: CardCheckpoint, pending: PendingOperation, ack: CardKitAck) -> None:
        if not isinstance(ack, CardKitAck):
            raise CardKitStateError("invalid_cardkit_ack")
        if pending.kind == "create" and not ack.card_id:
            raise CardKitStateError("missing_created_card_id")
        if pending.kind == "send" and not ack.message_id:
            raise CardKitStateError("missing_sent_message_id")
        if ack.card_id is not None and current.card_id is not None and ack.card_id != current.card_id:
            raise CardKitStateError("cardkit_ack_card_mismatch")
        if ack.message_id is not None and current.message_id is not None and ack.message_id != current.message_id:
            raise CardKitStateError("cardkit_ack_message_mismatch")
        if ack.sequence is not None and ack.sequence != pending.sequence:
            raise CardKitStateError("cardkit_ack_sequence_mismatch")

    def reject(self, scope: CardScope, operation_id: str) -> CardCheckpoint:
        with self._lock:
            current, pending = self._pending(scope, operation_id)
            phase = {"create": "new", "send": "created", "update": "streaming", "close": "fallback_pending"}[
                pending.kind
            ]
            checkpoint = replace(current, version=current.version + 1, phase=phase, pending=None)
            self._checkpoints[scope.key] = checkpoint
            return checkpoint

    def mark_uncertain(self, scope: CardScope, operation_id: str) -> CardCheckpoint:
        with self._lock:
            current, _ = self._pending(scope, operation_id)
            checkpoint = replace(current, phase="uncertain", version=current.version + 1)
            self._checkpoints[scope.key] = checkpoint
            return checkpoint

    def reconcile(
        self,
        scope: CardScope,
        *,
        operation_id: str,
        delivered: bool,
        evidence_ref: str,
        card_id: str | None = None,
        message_id: str | None = None,
    ) -> CardCheckpoint:
        """Caller-supplied verified evidence, not a remote lookup or an automatic retry."""
        if type(delivered) is not bool:
            raise CardKitStateError("cardkit_reconciliation_requires_boolean")
        identifier(evidence_ref)
        with self._lock:
            current, pending = self._pending(scope, operation_id)
            if current.phase != "uncertain":
                raise CardKitStateError("cardkit_reconciliation_requires_uncertain")
            if delivered:
                ack = CardKitAck(card_id=card_id, message_id=message_id, sequence=pending.sequence)
                checkpoint = self.confirm(scope, operation_id, ack)
            else:
                if card_id is not None or message_id is not None:
                    raise CardKitStateError("cardkit_unsent_proof_has_remote_receipt")
                checkpoint = self.reject(scope, operation_id)
            checkpoint = replace(checkpoint, version=checkpoint.version + 1, evidence_ref=evidence_ref)
            self._checkpoints[scope.key] = checkpoint
            return checkpoint

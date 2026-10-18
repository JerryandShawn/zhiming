"""Offline CardKit orchestration with explicit acknowledgements and no default network transport.

Every candidate wire operation below is 待对照飞书官方文档核实. A snapshot test
can recover metadata, but production needs durable outbox writes and a fenced
lease; callers must stop the old worker before recovering on another process.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC
from threading import RLock
from typing import Any

from mingjing_core.timekit.clock import Clock

from .cardkit_contracts import (
    CardCheckpoint,
    CardKitAck,
    CardKitRejected,
    CardKitResult,
    CardKitStateError,
    CardKitTransport,
    CardScope,
    FallbackIntent,
    OperationKind,
    PendingOperation,
    canonical,
    fingerprint,
    identifier,
)
from .cardkit_store import MemoryCardKitStore


def _card(value: Mapping[str, Any], *, streaming: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CardKitStateError("cardkit_layout_must_be_an_object")
    try:
        card = json.loads(canonical(dict(value)))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise CardKitStateError("invalid_cardkit_layout") from None
    if card.get("schema") != "2.0":  # 待对照飞书官方文档核实；这里只按08候选布局防空输入。
        raise CardKitStateError("cardkit_requires_json_2_layout")
    body = card.get("body")  # 待对照飞书官方文档核实。
    elements = body.get("elements") if isinstance(body, dict) else None  # 待对照飞书官方文档核实。
    if not isinstance(elements, list) or not elements or any(not isinstance(item, dict) for item in elements):
        raise CardKitStateError("cardkit_requires_body_elements")
    config = card.setdefault("config", {})  # 待对照飞书官方文档核实。
    if not isinstance(config, dict):
        raise CardKitStateError("invalid_cardkit_config")
    config["streaming_mode"] = streaming  # 待对照飞书官方文档核实。
    return card


class CardKitClient:
    def __init__(
        self,
        scope: CardScope,
        *,
        transport: CardKitTransport,
        clock: Clock,
        store: MemoryCardKitStore,
        interval_ms: int = 400,
        element_id: str = "answer",
    ) -> None:
        if transport is None or not all(
            callable(getattr(transport, name, None)) for name in ("create", "send", "update", "close")
        ):
            raise CardKitStateError("cardkit_requires_an_explicit_transport")
        if type(interval_ms) is not int or not 300 <= interval_ms <= 500:
            raise CardKitStateError("cardkit_interval_must_be_300_to_500_ms")
        identifier(element_id)  # 待对照飞书官方文档核实。
        self.scope, self.transport, self.clock, self.store = scope, transport, clock, store
        self.interval_ms, self.element_id = interval_ms, element_id
        self._buffer_lock = RLock()
        self._text_pending: tuple[str, str] | None = None
        self._final_pending: tuple[dict[str, Any], str] | None = None

    def _now_ms(self) -> int:
        instant = self.clock.now()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise CardKitStateError("cardkit_clock_requires_timezone")
        stamp = int(instant.astimezone(UTC).timestamp() * 1000)
        if stamp < 0:
            raise CardKitStateError("cardkit_clock_before_epoch")
        return stamp

    def start(self, initial_card: Mapping[str, Any]) -> CardKitResult:
        layout = _card(initial_card, streaming=True)
        digest = fingerprint(layout)
        current = self.store.get(self.scope)
        if current.initial_fingerprint not in {None, digest}:
            raise CardKitStateError("cardkit_initial_payload_changed")
        if current.pending is not None:
            return self._result(current)
        if current.phase == "new":
            result = self._perform("create", layout, digest)
            if result.status != "created":
                return result
            current = result.checkpoint
        if current.phase == "created":
            return self._perform("send", None, fingerprint([current.card_id, self.scope.open_id]))
        return self._result(current)

    def offer_text(self, full_text: str) -> None:
        if not isinstance(full_text, str):
            raise CardKitStateError("cardkit_text_must_be_a_string")
        current = self.store.get(self.scope)
        if current.phase in {"closed", "fallback_pending"}:
            raise CardKitStateError("cardkit_already_finalized")
        with self._buffer_lock:
            if self._final_pending is not None:
                raise CardKitStateError("cardkit_finalization_pending")
            self._text_pending = full_text, fingerprint(full_text)

    def flush(self) -> CardKitResult:
        current = self.store.get(self.scope)
        if current.pending is not None or current.phase in {"closed", "fallback_pending"}:
            return self._result(current)
        if current.phase != "streaming":
            return self._result(current, status="needs_initial_send")
        with self._buffer_lock:
            pending = self._final_pending or self._text_pending
            closing = self._final_pending is not None
        if pending is None:
            return self._result(current, status="noop")
        payload, digest = pending
        if not closing and current.last_text_fingerprint == digest:
            return self._result(current, status="noop")
        now_ms = self._now_ms()
        due = (current.last_attempt_ms or 0) + self.interval_ms
        if current.last_attempt_ms is not None and now_ms < current.last_attempt_ms:
            raise CardKitStateError("cardkit_clock_went_backwards")
        if now_ms < due:
            return CardKitResult("deferred", current, next_due_ms=due)
        return self._perform("close" if closing else "update", payload, digest)

    def finish(self, final_card: Mapping[str, Any]) -> CardKitResult:
        layout = _card(final_card, streaming=False)
        digest = fingerprint(layout)
        current = self.store.get(self.scope)
        if current.final_fingerprint not in {None, digest}:
            raise CardKitStateError("cardkit_final_payload_changed")
        if current.phase in {"closed", "fallback_pending"}:
            return self._result(current)
        with self._buffer_lock:
            if self._final_pending is not None and self._final_pending[1] != digest:
                raise CardKitStateError("cardkit_final_payload_changed")
            self._final_pending, self._text_pending = (layout, digest), None
        return self.flush()

    def recover(self, authoritative_final_card: Mapping[str, Any]) -> CardKitResult:
        """Never create/send here; final text must come from an authorized persisted run."""
        current = self.store.get(self.scope)
        if current.pending is not None:
            return self._result(current)
        if current.card_id is None or current.message_id is None:
            return self._result(current, status="needs_initial_send")
        return self.finish(authoritative_final_card)

    def snapshot(self) -> dict[str, Any]:
        """No text, final layout, preview or private exception diagnostics enter the snapshot."""
        return self.store.snapshot(self.scope)

    def reconcile(
        self,
        *,
        operation_id: str,
        delivered: bool,
        evidence_ref: str,
        card_id: str | None = None,
        message_id: str | None = None,
    ) -> CardKitResult:
        """Receipt fields are 待对照飞书官方文档核实; caller must verify evidence outside this offline module."""
        checkpoint = self.store.reconcile(
            self.scope,
            operation_id=operation_id,
            delivered=delivered,
            evidence_ref=evidence_ref,
            card_id=card_id,
            message_id=message_id,
        )
        return self._result(checkpoint)

    def _perform(self, kind: OperationKind, payload: Any, digest: str) -> CardKitResult:
        current = self.store.get(self.scope)
        reserved = self.store.reserve(
            self.scope,
            expected_version=current.version,
            kind=kind,
            payload_fingerprint=digest,
            now_ms=self._now_ms(),
            interval_ms=self.interval_ms,
        )
        pending = reserved.pending
        if pending is None:
            raise CardKitStateError("cardkit_reservation_missing")
        try:
            ack = self._call_transport(reserved, pending, payload)
            checkpoint = self.store.confirm(self.scope, pending.operation_id, ack)
        except CardKitRejected:
            checkpoint = self.store.reject(self.scope, pending.operation_id)
            return self._result(checkpoint, status="rejected" if kind != "close" else "fallback_required")
        except Exception:
            checkpoint = self.store.mark_uncertain(self.scope, pending.operation_id)
            return self._result(checkpoint)
        if kind in {"update", "close"}:
            with self._buffer_lock:
                if kind == "close":
                    self._text_pending = self._final_pending = None
                elif self._text_pending is not None and self._text_pending[1] == digest:
                    self._text_pending = None
        return self._result(checkpoint)

    def _call_transport(self, state: CardCheckpoint, pending: PendingOperation, payload: Any) -> CardKitAck:
        """Every external method/field mapping here is 待对照飞书官方文档核实。"""
        if pending.kind == "create":
            return self.transport.create(payload, operation_id=pending.operation_id)
        if pending.kind == "send":
            return self.transport.send(state.card_id, self.scope.open_id, operation_id=pending.operation_id)
        if pending.kind == "update":
            return self.transport.update(
                state.card_id, self.element_id, payload, sequence=pending.sequence, operation_id=pending.operation_id
            )
        return self.transport.close(
            state.card_id, payload, sequence=pending.sequence, operation_id=pending.operation_id
        )

    @staticmethod
    def _result(state: CardCheckpoint, *, status: str | None = None) -> CardKitResult:
        fallback = None
        if state.phase == "fallback_pending":
            fallback = FallbackIntent(
                "cardkit-fallback:" + fingerprint([state.scope.key, state.final_fingerprint]),
                state.card_id,
                state.message_id,
                state.final_fingerprint,
            )
        resolved = "uncertain" if state.pending is not None else "fallback_required" if fallback else state.phase
        return CardKitResult(status or resolved, state, fallback_intent=fallback)

"""Atomic in-memory callback command reference. Production must use one PG token/command transaction."""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from mingjing_core.timekit.clock import Clock

from .action_token_contracts import (
    ActionTokenClaim,
    ActionTokenRecord,
    TokenConsumption,
)
from .action_token_store import MemoryActionTokenStore
from .action_tokens import ActionTokenService
from .callback_auth import CallbackError, VerifiedCallback


@dataclass(frozen=True)
class CallbackBinding:
    claim: ActionTokenClaim = field(repr=False)
    app_id: str
    chat_id: str = field(repr=False)
    message_id: str = field(repr=False)


@dataclass(frozen=True)
class CallbackCommand:
    operation_id: str
    claim: ActionTokenClaim = field(repr=False)
    queued_at: datetime


@dataclass(frozen=True)
class CallbackReceipt:
    operation_id: str
    duplicate: bool

    def response(self) -> dict:
        # Acknowledgement only, never a false business-success receipt or card.raw for an entity card.
        return {"toast": {"type": "info", "content": "操作已收到"}}


class MemoryCallbackCommands:
    """Holds only hashed capabilities/metadata. No network, plaintext user payloads, or silent retries."""

    def __init__(self, *, clock: Clock, capacity: int = 10_000) -> None:
        self._lock = threading.RLock()
        self._tokens = MemoryActionTokenStore(capacity=capacity)
        self._clock, self._capacity = clock, capacity
        self._events: dict[tuple[str, str], tuple[str, str]] = {}
        self._commands: dict[str, CallbackCommand] = {}
        self._states: dict[str, str] = {}

    def put_if_absent(self, record: ActionTokenRecord) -> bool:
        with self._lock:
            return self._tokens.put_if_absent(record)

    def consume(
        self, digest: str, claim: ActionTokenClaim, *, now: datetime
    ) -> TokenConsumption:
        # This API supports capability tests; callbacks must call accept() to atomically enqueue too.
        with self._lock:
            return self._tokens.consume(digest, claim, now=now)

    def accept(
        self,
        event: VerifiedCallback,
        binding: CallbackBinding,
        *,
        authorize: Callable[[ActionTokenClaim], bool],
    ) -> CallbackReceipt:
        if not isinstance(event, VerifiedCallback) or not isinstance(
            binding, CallbackBinding
        ):
            raise CallbackError()
        claim = binding.claim
        if not isinstance(claim, ActionTokenClaim) or (
            event.app_id,
            event.open_id,
            event.chat_id,
            event.message_id,
        ) != (binding.app_id, claim.open_id, binding.chat_id, binding.message_id):
            raise CallbackError()
        with self._lock:
            try:
                if authorize(claim) is not True:
                    raise CallbackError()
            except Exception:
                raise CallbackError() from None
            key = (event.app_id, event.event_id)
            previous = self._events.get(key)
            if previous is not None:
                if previous[0] != event.fingerprint:
                    raise CallbackError()
                return CallbackReceipt(previous[1], True)
            if len(self._events) >= self._capacity:
                raise CallbackError()
            try:
                consumption = ActionTokenService(self, clock=self._clock).consume(
                    event.action_token,
                    owner_id=claim.owner_id,
                    subject_id=claim.subject_id,
                    open_id=claim.open_id,
                    kind=claim.kind,
                    entity_id=claim.entity_id,
                    payload_fingerprint=claim.payload_fingerprint,
                )
            except Exception:
                raise CallbackError() from None
            operation = consumption.operation_id
            duplicate = operation in self._commands
            if consumption.replayed and not duplicate:
                # A token consumed outside this queue has no proof of an enqueued command.
                raise CallbackError()
            if not duplicate:
                self._commands[operation] = CallbackCommand(
                    operation, claim, self._clock.now()
                )
                self._states[operation] = "queued"
            self._events[key] = (event.fingerprint, operation)
            return CallbackReceipt(operation, duplicate)

    def execute_once(
        self,
        operation_id: str,
        *,
        authorize: Callable[[ActionTokenClaim], bool],
        execute: Callable[[CallbackCommand], None],
    ) -> str:
        """Test worker reference: reserve once, recheck authority, never resend unknown outcomes."""
        with self._lock:
            if operation_id not in self._commands:
                raise CallbackError()
            if self._states[operation_id] != "queued":
                return self._states[operation_id]
            command = self._commands[operation_id]
            self._states[operation_id] = "executing"
        try:
            if authorize(command.claim) is not True:
                result = "rejected"
            else:
                execute(command)
                result = "succeeded"
        except Exception:
            result = "unknown"
        with self._lock:
            self._states[operation_id] = result
        return result

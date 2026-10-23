"""Recording-only CardKit fake; no SDK credentials, sockets or production state."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from mingjing_core.adapters.channels.cardkit_client import CardKitClient
from mingjing_core.adapters.channels.cardkit_contracts import CardKitAck, CardScope
from mingjing_core.adapters.channels.cardkit_store import MemoryCardKitStore
from mingjing_core.timekit.clock import FrozenClock

SCOPE = CardScope("synthetic-owner", "synthetic-subject", "ou_synthetic", "synthetic-business")
INITIAL = {
    "schema": "2.0",
    "body": {
        "elements": [
            {"tag": "markdown", "element_id": "status", "content": "处理中"},
            {"tag": "markdown", "element_id": "answer", "content": ""},
        ]
    },
}
FINAL = {
    "schema": "2.0",
    "body": {
        "elements": [
            {"tag": "markdown", "element_id": "answer", "content": "PRIVATE_SYNTHETIC_FINAL"},
        ]
    },
}


@dataclass(frozen=True)
class RecordedCall:
    kind: str
    card_id: str | None
    sequence: int | None
    operation_id: str
    at_ms: int
    payload: Any = field(repr=False)


class RecordingTransport:
    def __init__(self, clock: FrozenClock) -> None:
        self.clock = clock
        self.calls: list[RecordedCall] = []
        self.fail_next: dict[str, BaseException | CardKitAck] = {}
        self.hook: Callable[[RecordedCall], None] | None = None

    def _record(
        self, kind: str, card_id: str | None, sequence: int | None, operation_id: str, payload: Any, ack: CardKitAck
    ) -> CardKitAck:
        call = RecordedCall(
            kind, card_id, sequence, operation_id, int(self.clock.now().timestamp() * 1000), copy.deepcopy(payload)
        )
        self.calls.append(call)
        if self.hook:
            self.hook(call)
        fault = self.fail_next.pop(kind, None)
        if isinstance(fault, BaseException):
            raise fault
        return fault if fault is not None else ack

    def create(self, card: Mapping[str, Any], *, operation_id: str) -> CardKitAck:
        return self._record("create", None, None, operation_id, card, CardKitAck(card_id="card-one"))

    def send(self, card_id: str, open_id: str, *, operation_id: str) -> CardKitAck:
        return self._record(
            "send", card_id, None, operation_id, open_id, CardKitAck(card_id=card_id, message_id="message-one")
        )

    def update(self, card_id: str, element_id: str, text: str, *, sequence: int, operation_id: str) -> CardKitAck:
        return self._record(
            "update",
            card_id,
            sequence,
            operation_id,
            {"element_id": element_id, "text": text},
            CardKitAck(card_id=card_id, sequence=sequence),
        )

    def close(self, card_id: str, final_card: Mapping[str, Any], *, sequence: int, operation_id: str) -> CardKitAck:
        return self._record(
            "close", card_id, sequence, operation_id, final_card, CardKitAck(card_id=card_id, sequence=sequence)
        )


def session(
    *,
    interval_ms: int = 400,
) -> tuple[CardKitClient, RecordingTransport, FrozenClock, MemoryCardKitStore]:
    clock = FrozenClock(datetime(2026, 10, 19, 2, tzinfo=UTC))
    transport, store = RecordingTransport(clock), MemoryCardKitStore()
    client = CardKitClient(SCOPE, transport=transport, clock=clock, store=store, interval_ms=interval_ms)
    return client, transport, clock, store

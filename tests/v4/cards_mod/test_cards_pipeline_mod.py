"""Offline cross-module flow with real candidate builders/services and only a fake wire boundary."""

import hashlib
import json
import socket
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.adapters.channels.action_tokens import ActionTokenService, MemoryActionTokenStore
from mingjing_core.adapters.channels.cardkit_client import CardKitClient
from mingjing_core.adapters.channels.cardkit_contracts import CardKitAck, CardScope
from mingjing_core.adapters.channels.cardkit_store import MemoryCardKitStore
from mingjing_core.adapters.channels.cards import answer_card, question_card
from mingjing_core.adapters.channels.cards_contracts import CardAction
from mingjing_core.timekit.clock import FrozenClock


class Wire:
    def __init__(self) -> None:
        self.operations: list[tuple] = []

    def create(self, card: dict, *, operation_id: str) -> CardKitAck:
        self.operations.append(("create", operation_id, card))
        return CardKitAck(card_id="synthetic-card")

    def send(self, card_id: str, open_id: str, *, operation_id: str) -> CardKitAck:
        self.operations.append(("send", operation_id, card_id, open_id))
        return CardKitAck(message_id="synthetic-message")

    def update(self, card_id: str, element_id: str, text: str, *, sequence: int, operation_id: str) -> CardKitAck:
        self.operations.append(("update", sequence, card_id, element_id, text))
        return CardKitAck(card_id=card_id, sequence=sequence)

    def close(self, card_id: str, final_card: dict, *, sequence: int, operation_id: str) -> CardKitAck:
        self.operations.append(("close", sequence, card_id, final_card))
        return CardKitAck(card_id=card_id, sequence=sequence)


@pytest.fixture(autouse=True)
def no_wire_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Offline module attempted an external connection")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def test_stream_reset_recovery_same_card_then_identity_bound_question_once() -> None:
    clock = FrozenClock(datetime(2026, 10, 19, 1, tzinfo=UTC))
    wire = Wire()
    scope = CardScope("synthetic-owner", "self", "ou_synthetic", "synthetic-run")
    client = CardKitClient(scope, transport=wire, clock=clock, store=MemoryCardKitStore())
    assert client.start(answer_card("", streaming=True)).status == "streaming"
    clock.advance(timedelta(milliseconds=400))
    client.offer_text("合成旧草稿")
    assert client.flush().status == "streaming"
    client.offer_text("")
    assert client.flush().status == "deferred"
    clock.advance(timedelta(milliseconds=400))
    assert client.flush().status == "streaming"
    assert wire.operations[-1][4] == ""

    token_service = ActionTokenService(MemoryActionTokenStore(), clock=clock)
    expected = {
        "owner_id": scope.owner_id,
        "subject_id": scope.subject_id,
        "open_id": scope.open_id,
        "kind": "question.answer",
        "entity_id": "synthetic-question",
        "payload_fingerprint": hashlib.sha256(b"question-revision1-option-a").hexdigest(),
    }
    issued = token_service.issue(**expected)
    final = question_card("合成问题？", why="需要确认选项", options=[CardAction("合成选项", issued.token)])
    snapshot = client.snapshot()
    assert "合成旧草稿" not in json.dumps(snapshot, ensure_ascii=False)
    assert issued.token not in json.dumps(snapshot, ensure_ascii=False)
    replacement = CardKitClient(
        scope, transport=wire, clock=clock, store=MemoryCardKitStore.from_snapshot(snapshot, scope=scope)
    )
    clock.advance(timedelta(milliseconds=400))
    assert replacement.recover(final).status == "closed"
    assert [operation[0] for operation in wire.operations] == ["create", "send", "update", "update", "close"]
    assert [operation[1] for operation in wire.operations[2:]] == [1, 2, 3]
    assert {operation[2] for operation in wire.operations[2:]} == {"synthetic-card"}
    assert wire.operations[-1][3]["config"]["streaming_mode"] is False

    consumed = token_service.consume(issued.token, **expected)
    assert consumed.should_execute
    replay = token_service.consume(issued.token, **expected)
    assert not replay.should_execute and replay.operation_id == consumed.operation_id
    selected = question_card(
        "合成问题？", why="需要确认选项", options=[CardAction("合成选项", issued.token)], selected_label="合成选项"
    )
    assert not any(element["tag"] == "button" for element in selected["body"]["elements"])

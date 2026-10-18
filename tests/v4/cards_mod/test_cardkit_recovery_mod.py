"""Crash points, reconciliation requirements and same-card completion without blind replay."""

from __future__ import annotations

import copy
import json
from datetime import timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_client import CardKitClient
from mingjing_core.adapters.channels.cardkit_contracts import CardKitRejected, CardKitStateError
from mingjing_core.adapters.channels.cardkit_store import MemoryCardKitStore
from tests.v4.cards_mod._cardkit_fixture_mod import FINAL, INITIAL, SCOPE, RecordingTransport, session


class SimulatedProcessCrash(BaseException):
    """Escape ordinary error handling exactly where a process may disappear."""


@pytest.mark.parametrize("kind", ["create", "send", "update", "close"])
def test_every_unknown_operation_stays_blocked_after_snapshot_restore_until_explicit_reconciliation(kind: str) -> None:
    client, transport, clock, _ = session()
    if kind in {"update", "close"}:
        client.start(INITIAL)
        clock.advance(timedelta(milliseconds=400))
    transport.fail_next[kind] = TimeoutError("PRIVATE_UNKNOWN_BODY")
    if kind in {"create", "send"}:
        result = client.start(INITIAL)
    elif kind == "update":
        client.offer_text("private partial")
        result = client.flush()
    else:
        result = client.finish(FINAL)
    assert result.status == "uncertain" and result.fallback_intent is None
    pending = result.checkpoint.pending
    assert pending is not None and pending.kind == kind
    fresh_transport = RecordingTransport(clock)
    restored = MemoryCardKitStore.from_snapshot(client.snapshot(), scope=SCOPE)
    fresh = CardKitClient(SCOPE, transport=fresh_transport, clock=clock, store=restored)
    clock.advance(timedelta(hours=1))
    assert fresh.start(INITIAL).status == fresh.flush().status == fresh.recover(FINAL).status == "uncertain"
    assert fresh_transport.calls == []
    assert "PRIVATE_UNKNOWN_BODY" not in json.dumps(fresh.snapshot())


@pytest.mark.parametrize("kind", ["create", "send"])
def test_confirmed_create_or_send_after_unknown_does_not_repeat_that_external_step(kind: str) -> None:
    client, transport, clock, _ = session()
    transport.fail_next[kind] = TimeoutError("unknown")
    result = client.start(INITIAL)
    pending = result.checkpoint.pending
    assert pending
    receipt = {"card_id": "recovered-card"} if kind == "create" else {"message_id": "recovered-message"}
    reconciled = client.reconcile(
        operation_id=pending.operation_id, delivered=True, evidence_ref="proof:remote", **receipt
    )
    assert reconciled.status == ("created" if kind == "create" else "streaming")
    before = len(transport.calls)
    if kind == "create":
        assert client.start(INITIAL).status == "streaming"
        assert [call.kind for call in transport.calls[before:]] == ["send"]
    clock.advance(timedelta(milliseconds=400))
    closed = client.recover(FINAL)
    assert closed.status == "closed"
    assert transport.calls[-1].card_id == ("recovered-card" if kind == "create" else "card-one")
    assert sum(call.kind == "create" for call in transport.calls) == 1


@pytest.mark.parametrize("kind", ["create", "send"])
def test_missing_real_remote_receipt_does_not_unlock_unknown_create_or_send(kind: str) -> None:
    client, transport, _, _ = session()
    transport.fail_next[kind] = TimeoutError("unknown")
    pending = client.start(INITIAL).checkpoint.pending
    assert pending
    with pytest.raises(CardKitStateError, match="missing_"):
        client.reconcile(operation_id=pending.operation_id, delivered=True, evidence_ref="proof:incomplete")
    assert client.store.get(SCOPE).phase == "uncertain"


def test_proven_unsent_send_reuses_existing_card_and_stable_send_operation_id() -> None:
    client, transport, _, _ = session()
    transport.fail_next["send"] = TimeoutError("unknown")
    pending = client.start(INITIAL).checkpoint.pending
    assert pending and pending.kind == "send"
    assert (
        client.reconcile(operation_id=pending.operation_id, delivered=False, evidence_ref="proof:not-sent").status
        == "created"
    )
    assert client.start(INITIAL).status == "streaming"
    sends = [call for call in transport.calls if call.kind == "send"]
    assert len(sends) == 2 and sends[0].operation_id == sends[1].operation_id
    assert sends[0].card_id == sends[1].card_id == "card-one"
    assert sum(call.kind == "create" for call in transport.calls) == 1


def test_unknown_update_proven_unsent_burns_sequence_then_authoritative_final_closes_same_card() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    client.offer_text("partial")
    clock.advance(timedelta(milliseconds=400))
    transport.fail_next["update"] = TimeoutError("unknown")
    pending = client.flush().checkpoint.pending
    assert pending and pending.sequence == 1
    reconciled = client.reconcile(operation_id=pending.operation_id, delivered=False, evidence_ref="proof:not-applied")
    assert reconciled.checkpoint.last_reserved_sequence == 1 and reconciled.checkpoint.last_acked_sequence == 0
    clock.advance(timedelta(milliseconds=400))
    closed = client.recover(FINAL)
    assert closed.status == "closed" and closed.checkpoint.last_acked_sequence == 2
    assert [(call.kind, call.card_id, call.sequence) for call in transport.calls[-2:]] == [
        ("update", "card-one", 1),
        ("close", "card-one", 2),
    ]


def test_reserved_but_crashed_update_cannot_be_replayed_by_a_new_client() -> None:
    client, transport, clock, store = session()
    client.start(INITIAL)
    client.offer_text("PRIVATE_PARTIAL")
    clock.advance(timedelta(milliseconds=400))
    transport.fail_next["update"] = SimulatedProcessCrash()
    with pytest.raises(SimulatedProcessCrash):
        client.flush()
    assert store.get(SCOPE).phase == "in_flight" and store.get(SCOPE).last_reserved_sequence == 1
    restored_store = MemoryCardKitStore.from_snapshot(client.snapshot(), scope=SCOPE)
    fresh_transport = RecordingTransport(clock)
    fresh = CardKitClient(SCOPE, transport=fresh_transport, clock=clock, store=restored_store)
    assert fresh.recover(FINAL).status == "uncertain" and fresh_transport.calls == []
    assert "PRIVATE_PARTIAL" not in json.dumps(fresh.snapshot())


def test_successfully_acked_snapshot_recovery_uses_only_same_card_and_requires_explicit_final_layout() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    client.offer_text("PRIVATE_UNSAVED_BUFFER")
    restored = MemoryCardKitStore.from_snapshot(client.snapshot(), scope=SCOPE)
    fresh_transport = RecordingTransport(clock)
    fresh = CardKitClient(SCOPE, transport=fresh_transport, clock=clock, store=restored)
    with pytest.raises(CardKitStateError):
        fresh.recover(None)
    assert fresh_transport.calls == [] and not restored.durable
    clock.advance(timedelta(milliseconds=400))
    assert fresh.recover(FINAL).status == "closed"
    assert [(call.kind, call.card_id) for call in fresh_transport.calls] == [("close", "card-one")]
    assert "PRIVATE_UNSAVED_BUFFER" not in repr(fresh_transport.calls)
    assert len(transport.calls) == 2


def test_close_rejection_yields_stable_fallback_intent_without_sending_or_claiming_the_card_closed() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    clock.advance(timedelta(milliseconds=400))
    transport.fail_next["close"] = CardKitRejected("PRIVATE_REMOTE_REJECTION")
    first = client.finish(FINAL)
    assert first.status == "fallback_required" and first.checkpoint.phase == "fallback_pending"
    assert first.fallback_intent and first.fallback_intent.reason == "close_rejected"
    assert "PRIVATE_SYNTHETIC_FINAL" not in repr(first) + json.dumps(client.snapshot())
    assert client.flush().fallback_intent == client.finish(FINAL).fallback_intent == first.fallback_intent
    assert client.recover(FINAL).fallback_intent == first.fallback_intent
    assert [call.kind for call in transport.calls] == ["create", "send", "close"]


def test_unknown_close_confirmed_applied_closes_without_new_mutation_or_fallback() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    clock.advance(timedelta(milliseconds=400))
    transport.fail_next["close"] = TimeoutError("unknown")
    pending = client.finish(FINAL).checkpoint.pending
    assert pending
    result = client.reconcile(operation_id=pending.operation_id, delivered=True, evidence_ref="proof:closed")
    assert result.status == "closed" and result.fallback_intent is None
    assert client.finish(FINAL).status == "closed" and len(transport.calls) == 3


@pytest.mark.parametrize(
    "change",
    [
        {"durable": True},
        {"schema": "made-up-v2"},
        {"private_body": "not permitted"},
    ],
)
def test_snapshot_schema_does_not_accept_extra_private_fields_or_durability_claims(change: dict[str, object]) -> None:
    client, _, _, _ = session()
    client.start(INITIAL)
    snapshot = client.snapshot()
    snapshot.update(change)
    with pytest.raises(CardKitStateError):
        MemoryCardKitStore.from_snapshot(snapshot, scope=SCOPE)


@pytest.mark.parametrize(
    "field,value",
    [
        ("last_acked_sequence", 100),
        ("last_reserved_sequence", True),
        ("version", -1),
        ("last_attempt_ms", -1),
        ("initial_fingerprint", "not-a-hash"),
        ("phase", "closed"),
        ("message_id", None),
        ("card_id", "\ninvalid"),
        ("scope", {}),
    ],
)
def test_malformed_checkpoint_metadata_is_refused_without_transport(field: str, value: object) -> None:
    client, transport, _, _ = session()
    client.start(INITIAL)
    snapshot = copy.deepcopy(client.snapshot())
    snapshot["checkpoint"][field] = value
    with pytest.raises(CardKitStateError):
        MemoryCardKitStore.from_snapshot(snapshot, scope=SCOPE)
    assert len(transport.calls) == 2


def test_reconciliation_cannot_apply_stale_operation_wrong_card_or_non_boolean_proof() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    clock.advance(timedelta(milliseconds=400))
    client.offer_text("partial")
    transport.fail_next["update"] = TimeoutError("unknown")
    pending = client.flush().checkpoint.pending
    assert pending
    for changes in ({"operation_id": "stale-op"}, {"delivered": 1}, {"evidence_ref": ""}, {"card_id": "other-card"}):
        kwargs = {"operation_id": pending.operation_id, "delivered": True, "evidence_ref": "proof:valid", **changes}
        with pytest.raises(CardKitStateError):
            client.reconcile(**kwargs)
    assert client.store.get(SCOPE).phase == "uncertain" and len(transport.calls) == 3

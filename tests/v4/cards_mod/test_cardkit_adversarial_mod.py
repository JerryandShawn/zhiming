"""Independent lifecycle and fault injection; all transport methods are recording substitutes."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_client import CardKitClient
from mingjing_core.adapters.channels.cardkit_contracts import CardKitAck, CardKitStateError, CardScope
from mingjing_core.adapters.channels.cardkit_store import MemoryCardKitStore
from mingjing_core.timekit.clock import FrozenClock

SCOPE = CardScope("synthetic-owner", "self", "ou_SyntheticUser", "synthetic-business")


def layout(text: str = "合成最终回答") -> dict:
    return {"schema": "2.0", "body": {"elements": [{"tag": "markdown", "element_id": "answer", "content": text}]}}


class RecordingTransport:
    def __init__(self, *, fail: str | None = None, wrong_sequence: bool = False) -> None:
        self.fail = fail
        self.wrong_sequence = wrong_sequence
        self.calls: list[tuple] = []

    def _record(self, kind: str, *values) -> None:
        self.calls.append((kind, *values))
        if self.fail == kind:
            raise RuntimeError("synthetic-private-remote-response-XYZ")

    def create(self, card, *, operation_id):
        self._record("create", operation_id)
        return CardKitAck(card_id="synthetic-card")

    def send(self, card_id, open_id, *, operation_id):
        self._record("send", card_id, open_id, operation_id)
        return CardKitAck(card_id=card_id, message_id="synthetic-message")

    def update(self, card_id, element_id, text, *, sequence, operation_id):
        self._record("update", card_id, sequence, operation_id)
        return CardKitAck(card_id=card_id, sequence=sequence + int(self.wrong_sequence))

    def close(self, card_id, final_card, *, sequence, operation_id):
        self._record("close", card_id, sequence, operation_id)
        return CardKitAck(card_id=card_id, sequence=sequence)


def setup(*, fail: str | None = None):
    transport = RecordingTransport(fail=fail)
    clock = FrozenClock(datetime(2026, 10, 19, tzinfo=UTC))
    store = MemoryCardKitStore()
    client = CardKitClient(SCOPE, transport=transport, clock=clock, store=store)
    return client, transport, clock, store


def restored(client, transport, clock):
    store = MemoryCardKitStore.from_snapshot(client.snapshot(), scope=SCOPE)
    return CardKitClient(SCOPE, transport=transport, clock=clock, store=store), store


@pytest.mark.parametrize("kind", ["create", "send"])
def test_unknown_initial_operation_cannot_recreate_or_resend_after_fresh_client(kind: str) -> None:
    client, transport, clock, _ = setup(fail=kind)
    assert client.start(layout("合成初始状态")).status == "uncertain"
    original_calls = tuple(transport.calls)
    fresh, _ = restored(client, transport, clock)
    for _ in range(3):
        assert fresh.start(layout("合成初始状态")).status == "uncertain"
        assert fresh.recover(layout()).status == "uncertain"
    assert tuple(transport.calls) == original_calls


def test_same_business_cannot_change_target_to_bypass_an_unknown_send() -> None:
    client, transport, clock, store = setup(fail="send")
    assert client.start(layout()).status == "uncertain"
    before = tuple(transport.calls)
    another_target = replace(SCOPE, open_id="ou_AnotherTarget")
    with pytest.raises(CardKitStateError):
        CardKitClient(another_target, transport=transport, clock=clock, store=store).start(layout())
    assert tuple(transport.calls) == before


def test_live_in_flight_send_cannot_be_declared_unsent_and_retried() -> None:
    entered, release = threading.Event(), threading.Event()

    class BlockingSend(RecordingTransport):
        def send(self, card_id, open_id, *, operation_id):
            entered.set()
            assert release.wait(timeout=10)
            return super().send(card_id, open_id, operation_id=operation_id)

    transport, clock, store = BlockingSend(), FrozenClock(datetime(2026, 10, 19, tzinfo=UTC)), MemoryCardKitStore()
    client = CardKitClient(SCOPE, transport=transport, clock=clock, store=store)
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(client.start, layout())
        try:
            assert entered.wait(timeout=10)
            checkpoint = store.get(SCOPE)
            assert checkpoint.phase == "in_flight" and checkpoint.pending.kind == "send"
            with pytest.raises(CardKitStateError):
                client.reconcile(
                    operation_id=checkpoint.pending.operation_id,
                    delivered=False,
                    evidence_ref="synthetic-not-a-proof-of-live-request",
                )
            assert store.get(SCOPE).phase == "in_flight"
        finally:
            release.set()
        assert running.result(timeout=10).status == "streaming"
    assert [call[0] for call in transport.calls] == ["create", "send"]


def test_fresh_client_recovers_known_card_and_never_creates_or_sends_again() -> None:
    client, transport, clock, _ = setup()
    assert client.start(layout()).status == "streaming"
    client.offer_text("尚未发送的合成缓冲正文XYZ")
    fresh, _ = restored(client, transport, clock)
    clock.advance(timedelta(milliseconds=400))
    result = fresh.recover(layout("由授权运行提供的合成最终文本"))
    assert result.status == "closed"
    assert [call[0] for call in transport.calls] == ["create", "send", "close"]
    assert transport.calls[-1][1] == "synthetic-card"
    assert result.checkpoint.last_reserved_sequence == 1


def test_two_clients_same_scope_cannot_reserve_parallel_updates_or_reuse_sequence() -> None:
    entered, release = threading.Event(), threading.Event()

    class BlockingUpdate(RecordingTransport):
        def update(self, card_id, element_id, text, *, sequence, operation_id):
            if sequence == 1:
                entered.set()
                assert release.wait(timeout=10)
            return super().update(card_id, element_id, text, sequence=sequence, operation_id=operation_id)

    transport, clock, store = BlockingUpdate(), FrozenClock(datetime(2026, 10, 19, tzinfo=UTC)), MemoryCardKitStore()
    first = CardKitClient(SCOPE, transport=transport, clock=clock, store=store)
    second = CardKitClient(SCOPE, transport=transport, clock=clock, store=store)
    first.start(layout())
    first.offer_text("合成正文一")
    second.offer_text("合成正文二")
    clock.advance(timedelta(milliseconds=400))
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(first.flush)
        try:
            assert entered.wait(timeout=10)
            blocked = second.flush()
            assert blocked.checkpoint.phase == "in_flight" and blocked.checkpoint.pending.kind == "update"
            assert store.get(SCOPE).last_reserved_sequence == 1
        finally:
            release.set()
        assert running.result(timeout=10).status == "streaming"
    clock.advance(timedelta(milliseconds=400))
    assert second.flush().status == "streaming"
    assert [call[2] for call in transport.calls if call[0] == "update"] == [1, 2]


def test_unknown_update_requires_explicit_reconciliation_before_same_card_finalisation() -> None:
    client, transport, clock, _ = setup()
    client.start(layout())
    transport.fail = "update"
    client.offer_text("合成流式内容")
    clock.advance(timedelta(milliseconds=400))
    failed = client.flush()
    assert failed.status == "uncertain" and failed.checkpoint.last_reserved_sequence == 1
    fresh, store = restored(client, transport, clock)
    before = tuple(transport.calls)
    assert fresh.recover(layout()).status == "uncertain"
    assert tuple(transport.calls) == before
    pending = store.get(SCOPE).pending
    fresh.reconcile(operation_id=pending.operation_id, delivered=True, evidence_ref="verified-update-receipt")
    transport.fail = None
    clock.advance(timedelta(milliseconds=400))
    assert fresh.recover(layout()).status == "closed"
    assert [call[2] for call in transport.calls if call[0] in {"update", "close"}] == [1, 2]
    assert all(call[1] == "synthetic-card" for call in transport.calls if call[0] in {"update", "close"})


def test_unknown_close_is_not_a_known_failure_or_permission_to_send_fallback() -> None:
    client, transport, clock, _ = setup()
    client.start(layout())
    transport.fail = "close"
    clock.advance(timedelta(milliseconds=400))
    result = client.finish(layout())
    assert result.status == "uncertain" and result.fallback_intent is None
    fresh, _ = restored(client, transport, clock)
    before = tuple(transport.calls)
    assert fresh.recover(layout()).status == "uncertain"
    assert tuple(transport.calls) == before
    assert "synthetic-private-remote-response-XYZ" not in repr(result)


def test_closed_card_cannot_accept_new_text_or_different_final_layout() -> None:
    client, transport, clock, _ = setup()
    client.start(layout())
    clock.advance(timedelta(milliseconds=400))
    assert client.finish(layout()).status == "closed"
    before = tuple(transport.calls)
    assert client.recover(layout()).status == "closed"
    with pytest.raises(CardKitStateError):
        client.offer_text("晚到的合成新文本")
    with pytest.raises(CardKitStateError):
        client.recover(layout("另一个不匹配的最终回答"))
    assert tuple(transport.calls) == before


def test_wrong_ack_sequence_remains_unknown_and_next_proven_unsent_attempt_does_not_reuse_it() -> None:
    client, transport, clock, store = setup()
    client.start(layout())
    transport.wrong_sequence = True
    client.offer_text("合成流式内容")
    clock.advance(timedelta(milliseconds=400))
    assert client.flush().status == "uncertain"
    pending = store.get(SCOPE).pending
    client.reconcile(operation_id=pending.operation_id, delivered=False, evidence_ref="verified-unsent-update")
    transport.wrong_sequence = False
    clock.advance(timedelta(milliseconds=400))
    client.offer_text("合成流式内容")
    assert client.flush().status == "streaming"
    assert [call[2] for call in transport.calls if call[0] == "update"] == [1, 2]


def test_checkpoint_is_metadata_only_and_cross_scope_restore_is_rejected() -> None:
    client, transport, clock, _ = setup()
    client.start(layout("合成初始私密标记INITIAL"))
    client.offer_text("合成待发送私密标记BUFFER")
    clock.advance(timedelta(milliseconds=400))
    transport.fail = "close"
    client.finish(layout("合成最终私密标记FINAL"))
    snapshot = client.snapshot()
    raw = json.dumps(snapshot, ensure_ascii=False)
    assert all(marker not in raw for marker in ("INITIAL", "BUFFER", "FINAL", "synthetic-private-remote-response-XYZ"))
    assert snapshot["durable"] is False
    for field in ("owner_id", "subject_id", "open_id", "business_id"):
        with pytest.raises(CardKitStateError):
            MemoryCardKitStore.from_snapshot(snapshot, scope=replace(SCOPE, **{field: "different-scope"}))


@pytest.mark.parametrize("final", [None, {}, {"body": {"elements": []}}, {"schema": "1.0", "body": {"elements": []}}])
def test_recovery_requires_explicit_json2_final_layout_before_closing(final) -> None:
    client, transport, clock, _ = setup()
    client.start(layout())
    fresh, _ = restored(client, transport, clock)
    clock.advance(timedelta(milliseconds=400))
    before = tuple(transport.calls)
    with pytest.raises(CardKitStateError):
        fresh.recover(final)
    assert tuple(transport.calls) == before


def test_recover_with_no_known_initial_card_does_not_create_a_new_one() -> None:
    client, transport, _, _ = setup()
    result = client.recover(layout())
    assert result.status == "needs_initial_send" and not transport.calls

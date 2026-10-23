"""Normal streaming, coalescing, preflight gates and reservation-before-I/O invariants."""

from __future__ import annotations

import copy
import json
from datetime import timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_client import CardKitClient
from mingjing_core.adapters.channels.cardkit_contracts import CardKitAck, CardKitRejected, CardKitStateError
from tests.v4.cards_mod._cardkit_fixture_mod import FINAL, INITIAL, SCOPE, session


def test_full_stream_coalesces_text_resets_and_closes_explicitly_with_reserved_monotone_sequences() -> None:
    client, transport, clock, store = session()
    before_initial, before_final = copy.deepcopy(INITIAL), copy.deepcopy(FINAL)

    def verify_reserved(call: object) -> None:
        pending = store.get(SCOPE).pending
        assert pending is not None and pending.operation_id == call.operation_id
        assert pending.sequence == call.sequence and pending.fingerprint

    transport.hook = verify_reserved
    assert client.start(INITIAL).status == "streaming"
    assert [call.kind for call in transport.calls] == ["create", "send"]
    assert transport.calls[0].payload["config"]["streaming_mode"] is True
    client.offer_text("第一个片段")
    assert client.flush().status == "deferred"
    clock.advance(timedelta(milliseconds=200))
    client.offer_text("第一段和第二段合并")
    assert client.flush().status == "deferred"
    clock.advance(timedelta(milliseconds=200))
    assert client.flush().status == "streaming"
    client.offer_text("修订后完整文本")
    clock.advance(timedelta(milliseconds=400))
    assert client.flush().status == "streaming"
    assert transport.calls[-1].payload["text"] == "修订后完整文本"
    assert client.finish(FINAL).status == "deferred"
    clock.advance(timedelta(milliseconds=400))
    result = client.flush()
    assert result.status == "closed"
    mutations = [call for call in transport.calls if call.sequence is not None]
    assert [call.sequence for call in mutations] == [1, 2, 3]
    assert all(right.at_ms - left.at_ms == 400 for left, right in zip(mutations, mutations[1:], strict=False))
    assert transport.calls[-1].payload["config"]["streaming_mode"] is False
    assert result.checkpoint.last_reserved_sequence == result.checkpoint.last_acked_sequence == 3
    assert before_initial == INITIAL and before_final == FINAL


@pytest.mark.parametrize("interval", [300, 400, 500])
def test_all_allowed_throttle_intervals_have_exact_boundary(interval: int) -> None:
    client, transport, clock, _ = session(interval_ms=interval)
    client.start(INITIAL)
    client.offer_text("one")
    clock.advance(timedelta(milliseconds=interval - 1))
    deferred = client.flush()
    assert deferred.status == "deferred" and len(transport.calls) == 2 and deferred.next_due_ms
    clock.advance(timedelta(milliseconds=1))
    assert client.flush().status == "streaming" and transport.calls[-1].sequence == 1


@pytest.mark.parametrize("interval", [True, False, 299, 501, 400.0, "400"])
def test_unverified_or_out_of_range_intervals_are_rejected(interval: int) -> None:
    with pytest.raises(CardKitStateError, match="interval"):
        session(interval_ms=interval)


def test_start_and_identical_text_are_fingerprint_idempotent_but_changed_initial_is_refused() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    assert client.start(copy.deepcopy(INITIAL)).status == "streaming" and len(transport.calls) == 2
    clock.advance(timedelta(milliseconds=400))
    client.offer_text("same")
    client.flush()
    client.offer_text("same")
    assert client.flush().status == "noop" and len(transport.calls) == 3
    changed = copy.deepcopy(INITIAL)
    changed["body"]["elements"][0]["content"] = "changed"
    with pytest.raises(CardKitStateError, match="initial_payload_changed"):
        client.start(changed)
    assert len(transport.calls) == 3


def test_finish_replaces_unsent_text_buffer_and_same_final_replay_never_reopens() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    client.offer_text("unsent partial")
    assert client.finish(FINAL).status == "deferred"
    with pytest.raises(CardKitStateError, match="finalization_pending"):
        client.offer_text("late delta")
    clock.advance(timedelta(milliseconds=400))
    assert client.flush().status == "closed"
    assert [call.kind for call in transport.calls] == ["create", "send", "close"]
    assert client.finish(copy.deepcopy(FINAL)).status == "closed"
    assert client.flush().status == "closed" and len(transport.calls) == 3
    with pytest.raises(CardKitStateError, match="already_finalized"):
        client.offer_text("late")
    changed = copy.deepcopy(FINAL)
    changed["body"]["elements"][0]["content"] = "changed final"
    with pytest.raises(CardKitStateError, match="final_payload_changed"):
        client.finish(changed)


@pytest.mark.parametrize(
    "layout",
    [
        None,
        {},
        [],
        {"schema": "1.0", "body": {"elements": [{}]}},
        {"schema": "2.0", "body": {"elements": []}},
        {"schema": "2.0", "body": {"elements": ["bad"]}},
    ],
)
def test_empty_or_invalid_candidate_layout_fails_before_any_transport(layout: object) -> None:
    client, transport, _, _ = session()
    with pytest.raises(CardKitStateError):
        client.start(layout)
    assert transport.calls == []


def test_explicit_transport_required_and_no_credentials_or_http_default_are_instantiated() -> None:
    client, _, clock, store = session()
    with pytest.raises(CardKitStateError, match="explicit_transport"):
        CardKitClient(SCOPE, transport=None, clock=clock, store=store)
    assert client.snapshot()["durable"] is False


def test_snapshots_and_repr_contain_no_buffer_body_layout_preview_or_upstream_error() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    client.offer_text("PRIVATE_SYNTHETIC_PARTIAL")
    snapshot = json.dumps(client.snapshot(), ensure_ascii=False)
    assert "PRIVATE_SYNTHETIC_PARTIAL" not in snapshot and "body" not in snapshot and "preview" not in snapshot
    clock.advance(timedelta(milliseconds=400))
    transport.fail_next["update"] = TimeoutError("PRIVATE_UPSTREAM_BODY")
    result = client.flush()
    assert result.status == "uncertain"
    assert "PRIVATE_UPSTREAM_BODY" not in repr(result) + json.dumps(client.snapshot())
    assert "PRIVATE_SYNTHETIC_PARTIAL" not in repr(client)


def test_known_rejected_update_burns_reserved_sequence_and_only_explicit_later_flush_can_retry() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    client.offer_text("retry candidate")
    clock.advance(timedelta(milliseconds=400))
    transport.fail_next["update"] = CardKitRejected("private upstream body")
    rejected = client.flush()
    assert rejected.status == "rejected" and rejected.checkpoint.last_reserved_sequence == 1
    assert rejected.checkpoint.last_acked_sequence == 0 and len(transport.calls) == 3
    assert client.flush().status == "deferred" and len(transport.calls) == 3
    clock.advance(timedelta(milliseconds=400))
    result = client.flush()
    assert result.status == "streaming" and result.checkpoint.last_acked_sequence == 2
    assert [call.sequence for call in transport.calls if call.sequence] == [1, 2]


@pytest.mark.parametrize("ack", [CardKitAck(card_id="different-card", sequence=1), CardKitAck(sequence=99), None, {}])
def test_malformed_or_mismatched_ack_is_unknown_and_never_blindly_retried(ack: object) -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    client.offer_text("x")
    clock.advance(timedelta(milliseconds=400))
    if ack is None:
        transport.update = lambda *args, **kwargs: None
    else:
        transport.fail_next["update"] = ack
    result = client.flush()
    assert result.status == "uncertain"
    count = len(transport.calls)
    clock.advance(timedelta(hours=1))
    assert client.flush().status == "uncertain" and len(transport.calls) == count


def test_clock_rollback_cannot_bypass_throttle() -> None:
    client, transport, clock, _ = session()
    client.start(INITIAL)
    client.offer_text("x")
    clock.advance(timedelta(milliseconds=-1))
    with pytest.raises(CardKitStateError, match="clock_went_backwards"):
        client.flush()
    assert len(transport.calls) == 2

"""Synthetic real pure-state lifecycles; no SDK, HTTP, credential, database or model is used."""

import json
import random
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.adapters.channels.cardkit_official_v3 import (
    ArtifactEvidence,
    OfficialAck,
    OfficialOutcome,
    OfficialPolicy,
    begin_dispatch,
    claim,
    classify_response,
    fallback_intent,
    merge_official_reconciliation,
    new_state,
    prepare_operation,
    recover_expired,
    restore_state,
    settle_ack,
    settle_outcome,
    state_metadata,
    stream_deadline_action,
)
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import ReconciliationBinding, namespace_fingerprint
from mingjing_core.adapters.channels.cards_official_v3 import answer_card
from mingjing_core.adapters.channels.stream_outbox_v2 import FreshnessEvidence, StreamScope, VersionEvidence
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = StreamScope("synthetic-owner", "synthetic-self", "outbox", "run", "business", "feishu", "ou_synthetic")
TOKEN = "synthetic-lease-token"
TEXT = "合成最终正文"


def envelope():
    return {
        "schema": "core4.0",
        "message_id": "assistant",
        "text": TEXT,
        "receipts": [],
        "used_fact_ids": [],
        "used_claim_ids": [],
        "asked": None,
        "options": None,
        "review": {"state": "passed", "reasons": []},
        "usage": {},
        "validation": {"valid": True, "status": "validated", "schema": "core4.0"},
        "meta": {
            "core_run": {"run_id": "run", "operation_id": "operation"},
            "subject_id": SCOPE.subject_id,
            "case_ids": [],
            "structural_warnings": [],
        },
    }


def artifact():
    return ArtifactEvidence(SCOPE, fingerprint(envelope()), 1, answer_card(TEXT))


def proof(state, clock, purpose):
    inner = state.lease_state
    digest = fingerprint("synthetic-current-version")
    versions = (
        VersionEvidence("source", "source", digest, digest),
        VersionEvidence("dependency", "profile", digest, digest),
    )
    return FreshnessEvidence(
        SCOPE,
        inner.intent.operation_id,
        inner.revision,
        purpose,
        clock.now(),
        "transaction",
        "succeeded",
        inner.intent.payload_fingerprint,
        fingerprint(envelope()),
        envelope(),
        versions,
        1,
        1,
        tuple((row.category, row.identity, row.expected_hash) for row in versions),
    )


def prepare(state, kind, clock, suffix="", payload=None):
    clock.advance(timedelta(milliseconds=400))
    if kind == "finalize" and payload is None:
        payload = artifact().final_card
    return prepare_operation(
        state, kind, payload, operation_id=f"synthetic-{kind}-{suffix}", artifact=artifact(), clock=clock
    )


def dispatch(prepared, clock):
    state, request = prepared.state, prepared.request
    state = claim(
        state,
        request,
        artifact=artifact(),
        evidence=proof(state, clock, "claim"),
        token=TOKEN,
        worker_id="worker",
        clock=clock,
        ttl=timedelta(seconds=60),
        expected_revision=state.revision,
    )
    return begin_dispatch(
        state,
        request,
        artifact=artifact(),
        evidence=proof(state, clock, "dispatch"),
        token=TOKEN,
        fence=state.lease_state.fence,
        clock=clock,
        expected_revision=state.revision,
    )


def ack(state, clock):
    card = "card" if state.operation.kind == "create" else state.card_id
    message = "message" if state.operation.kind == "send" else state.message_id
    receipt = OfficialAck(card, message, state.operation.sequence)
    return settle_ack(
        state,
        receipt,
        evidence_ref="synthetic-response",
        token=TOKEN,
        fence=state.lease_state.fence,
        clock=clock,
        expected_revision=state.revision,
    )


def ready(policy=None):
    clock, state = FrozenClock(AT), new_state(SCOPE, policy)
    for kind in ("create", "send"):
        state = ack(dispatch(prepare(state, kind, clock), clock), clock)
    return state, clock


def outcome(state, clock, status, reason="synthetic-reason", after_ms=0, action_required=None):
    return settle_outcome(
        state,
        OfficialOutcome(status, reason, after_ms, action_required),
        evidence_ref="synthetic-proof",
        token=TOKEN,
        fence=state.lease_state.fence,
        clock=clock,
        expected_revision=state.revision,
    )


def test_full_finalize_and_settings_are_two_sequences_and_two_acks():
    state, clock = ready()
    update = prepare(state, "update", clock, payload=TEXT[:3])
    assert update.request.body["content"] == TEXT[:3]
    state = ack(dispatch(update, clock), clock)
    final = prepare(state, "finalize", clock)
    assert final.request.method == "PUT" and "card" in final.request.body
    state = ack(dispatch(final, clock), clock)
    assert state.finalize_acked and not state.close_acked and state.stage == "finalized"
    close = prepare(state, "close_streaming", clock)
    assert close.request.sequence == final.request.sequence + 1 and close.request.method == "PATCH"
    settings = json.loads(close.request.body["settings"])
    assert settings["config"]["streaming_mode"] is False
    assert settings["config"]["summary"] == artifact().final_card["config"]["summary"]
    state = ack(dispatch(close, clock), clock)
    assert state.stage == "closed" and state.card_id == "card" and state.message_id == "message"


@pytest.mark.parametrize("kind", ["update", "finalize", "close_streaming"])
def test_unknown_and_crash_restore_never_prepare_a_new_send(kind):
    state, clock = ready()
    if kind == "close_streaming":
        state = ack(dispatch(prepare(state, "finalize", clock), clock), clock)
    current = prepare(state, kind, clock, payload=TEXT if kind == "update" else None)
    state = dispatch(current, clock)
    restored = restore_state(state_metadata(state), scope=SCOPE)
    assert restored.phase == "uncertain" and restored.card_id == "card"
    with pytest.raises(ValueError):
        prepare(restored, kind, clock, "retry", payload=TEXT if kind == "update" else None)


def test_empty_reset_noops_without_sequence_or_request():
    state, clock = ready()
    empty = prepare_operation(state, "update", "", operation_id="reset", artifact=artifact(), clock=clock)
    assert empty.status == "noop_empty" and empty.state is state and empty.request is None


def test_close_rejection_plans_one_retry_then_stops_without_fallback():
    state, clock = ready()
    state = ack(dispatch(prepare(state, "finalize", clock), clock), clock)
    for index in range(2):
        current = prepare(state, "close_streaming", clock, str(index))
        state = outcome(dispatch(current, clock), clock, "rejected", "cardkit_10002")
    assert state.stage == "streaming_close_failed" and state.close_retries == 1
    assert state.finalize_acked and not state.close_acked
    with pytest.raises(ValueError):
        prepare(state, "close_streaming", clock, "third")


def test_finalize_refusal_only_produces_fallback_pending():
    state, clock = ready()
    state = outcome(dispatch(prepare(state, "finalize", clock), clock), clock, "rejected")
    assert state.stage == "fallback_pending" and not state.close_acked


@pytest.mark.parametrize(
    "gap,reason,expected",
    [(True, "rate_limited", 2), (False, "rate_limited", 1), (False, "cardkit_200810", 2), (False, "cardkit_300317", 2)],
)
def test_known_not_executed_retry_sequence_policy(gap, reason, expected):
    state, clock = ready(OfficialPolicy(allow_sequence_gaps=gap))
    state = outcome(dispatch(prepare(state, "update", clock, payload=TEXT), clock), clock, "retryable", reason)
    retry = prepare(state, "update", clock, "retry", TEXT)
    assert retry.request.sequence == expected


@pytest.mark.parametrize("code", [10002, 200740, 200750, 200860, 300302, 300311])
def test_permanent_error_table(code):
    assert classify_response(400, code).status == "rejected"


@pytest.mark.parametrize("code", [200810, 200850, 300309, 300317, 99991400])
def test_retryable_error_table(code):
    assert classify_response(400, code).status == "retryable"


@pytest.mark.parametrize("status,code", [(500, 0), (400, 200770), (400, 300120), (200, True), (200, 123456)])
def test_unknown_error_table(status, code):
    assert classify_response(status, code).status == "uncertain"


def test_rate_delay_and_timeout_host_decision():
    assert classify_response(429, None, {"X-Ogw-Ratelimit-Reset": "1.25"}).after_ms == 1250
    state, clock = ready()
    clock.advance(timedelta(minutes=10))
    assert stream_deadline_action(state, clock=clock) == "reopen_or_finalize"
    assert not state.close_acked and state.stage == "streaming"


def test_actual_wire_text_cannot_be_swapped_with_a_sidecar_validated_text():
    state, clock = ready()
    current = prepare(state, "update", clock, payload="完全不同的私密正文")
    with pytest.raises(ValueError):
        dispatch(current, clock)
    allowed = prepare(state, "update", clock, "good", TEXT)
    changed = replace(allowed.request, body={**allowed.request.body, "content": "另一个正文"})
    with pytest.raises(ValueError):
        dispatch(replace(allowed, request=changed), clock)


def test_thousand_frozen_clock_state_paths_keep_unknown_unsendable():
    rng = random.Random(26)
    for index in range(1000):
        state, clock = ready()
        current = prepare(state, "update", clock, str(index), TEXT[: rng.randint(1, len(TEXT))])
        state = dispatch(current, clock)
        if rng.randrange(2):
            state = outcome(state, clock, "uncertain")
        else:
            clock.advance(timedelta(seconds=61))
            state = recover_expired(state, clock=clock, expected_revision=state.revision)
        assert state.phase == "uncertain" and state.card_id == "card" and state.last_acked_sequence == 0
        with pytest.raises(ValueError):
            prepare(state, "update", clock, f"retry-{index}", TEXT)


@pytest.mark.parametrize(
    "key,value",
    [
        ("revision", True),
        ("last_reserved_sequence", 2_147_483_648),
        ("last_acked_sequence", "0"),
        ("close_acked", 1),
        ("finalize_acked", "false"),
        ("card_id", "c" * 21),
        ("started_at", "2026-10-21T00:00:00"),
        ("retry_kind", "update"),
        ("stage", "closed"),
        ("history", []),
    ],
)
def test_metadata_restore_rejects_bad_fields_or_missing_causal_history(key, value):
    state, _ = ready()
    data = state_metadata(state)
    if key == "history":
        value = [deepcopy(data["operation"]), deepcopy(data["operation"])]
    data[key] = value
    with pytest.raises(ValueError):
        restore_state(data, scope=SCOPE)


@pytest.mark.parametrize(
    "key,value", [("kind", "reopen"), ("sequence", True), ("wire_uuid", "fake"), ("content_fingerprint", "fake")]
)
def test_metadata_operation_is_strict(key, value):
    state, clock = ready()
    data = state_metadata(prepare(state, "update", clock, payload=TEXT).state)
    data["operation"][key] = value
    with pytest.raises(ValueError):
        restore_state(data, scope=SCOPE)


def test_crash_restore_increments_outer_revision_and_contains_no_payload_or_raw_token():
    state, clock = ready()
    state = dispatch(prepare(state, "update", clock, payload=TEXT), clock)
    data = state_metadata(state)
    assert TEXT not in json.dumps(data, ensure_ascii=False) and TOKEN not in json.dumps(data)
    restored = restore_state(data, scope=SCOPE)
    assert restored.phase == "uncertain" and restored.revision == state.revision + 1


def test_namespace_preserves_siblings_and_cas_and_never_resets_unknown():
    state, clock = ready()
    binding = ReconciliationBinding(**asdict(SCOPE))
    original = {"proof": {"verified": True}, "unrelated": [1, 2]}

    def merge(raw, value, revision):
        return merge_official_reconciliation(
            raw,
            binding=binding,
            state=value,
            current_row_revision=revision,
            expected_row_revision=revision,
            expected_namespace_fingerprint=namespace_fingerprint(raw),
        )

    first = merge(original, state, 0)
    raw = first.as_dict()
    assert raw["proof"] == original["proof"] and raw["unrelated"] == [1, 2]
    assert not merge(raw, state, 1).changed
    unknown = dispatch(prepare(state, "update", clock, payload=TEXT), clock)
    second = merge(raw, unknown, 1)
    with pytest.raises(ValueError):
        merge(second.as_dict(), replace(state, revision=unknown.revision + 1), 2)
    confirmed = ack(unknown, clock)
    assert merge(second.as_dict(), confirmed, 2).changed


def test_fallback_descriptor_only_exists_after_verified_finalize_refusal():
    state, clock = ready()
    assert fallback_intent(state) is None
    uncertain = outcome(dispatch(prepare(state, "finalize", clock), clock), clock, "uncertain")
    assert fallback_intent(uncertain) is None
    refused = outcome(dispatch(prepare(state, "finalize", clock, "refusal"), clock), clock, "rejected")
    intent = fallback_intent(refused)
    assert intent == fallback_intent(refused) and intent.card_id == "card" and intent.message_id == "message"


def test_prepared_finalize_metadata_cannot_claim_it_has_already_been_acked():
    state, clock = ready()
    data = state_metadata(prepare(state, "finalize", clock).state)
    data.update(stage="finalized", finalize_acked=True)
    with pytest.raises(ValueError):
        restore_state(data, scope=SCOPE)


def test_rate_limit_retries_do_not_consume_the_single_explicit_close_refusal_retry():
    state, clock = ready()
    state = ack(dispatch(prepare(state, "finalize", clock), clock), clock)
    for index in range(3):
        current = prepare(state, "close_streaming", clock, f"rate-{index}")
        state = outcome(dispatch(current, clock), clock, "retryable", "rate_limited", 400)
        assert state.close_retries == 0
    state = ack(dispatch(prepare(state, "close_streaming", clock, "success"), clock), clock)
    assert state.stage == "closed" and state.close_retries == 0


def test_namespace_does_not_preserve_malformed_legacy_proof_as_if_valid():
    state, _ = ready()
    binding = ReconciliationBinding(**asdict(SCOPE))
    raw = {
        "cardkit": {
            "schema": "cardkit.outbox.namespace.v2",
            "binding": asdict(binding),
            "revision": 0,
            "stream": {"phase": "acked"},
        }
    }
    with pytest.raises(ValueError):
        merge_official_reconciliation(
            raw,
            binding=binding,
            state=state,
            current_row_revision=0,
            expected_row_revision=0,
            expected_namespace_fingerprint=namespace_fingerprint(raw),
        )

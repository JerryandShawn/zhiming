"""Synthetic state-machine checks; no real transport, model, or authority is contacted."""

import json
import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import CardCheckpoint, CardScope, fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import (
    FreshnessEvidence,
    StreamError,
    StreamReceipt,
    StreamScope,
    VersionEvidence,
    acknowledge,
    begin_dispatch,
    claim,
    fallback_intent,
    mark_uncertain,
    next_intent,
    prepare_intent,
    reconcile,
    recover_expired,
    reject,
    renew,
    restore_state,
    state_metadata,
)
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = StreamScope("owner", "self", "outbox", "run", "business", "feishu", "ou_synthetic")
TOKEN = "synthetic-worker-token"
DIGEST = fingerprint({"synthetic": "card"})


def envelope():
    return {
        "schema": "core4.0",
        "message_id": "assistant",
        "text": "合成最终正文",
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
            "subject_id": "self",
            "case_ids": [],
            "structural_warnings": [],
        },
    }


def proof(state, clock, purpose="claim", **changes):
    body = envelope()
    versions = (
        VersionEvidence("source", "user-message", DIGEST, DIGEST),
        VersionEvidence("dependency", "profile-version", DIGEST, DIGEST),
    )
    base = FreshnessEvidence(
        state.scope,
        state.intent.operation_id,
        state.revision,
        purpose,
        clock.now(),
        "transaction",
        "succeeded",
        state.intent.payload_fingerprint,
        fingerprint(body),
        body,
        versions,
        1,
        1,
        tuple((item.category, item.identity, item.expected_hash) for item in versions),
    )
    return replace(base, **changes)


def initial(kind="create"):
    checkpoint = (
        None
        if kind == "create"
        else CardCheckpoint(
            CardScope("owner", "self", "ou_synthetic", "business"),
            phase="streaming",
            card_id="card",
            message_id="message",
            initial_fingerprint=DIGEST,
            last_reserved_sequence=4,
            last_acked_sequence=4,
        )
    )
    return prepare_intent(SCOPE, operation_id="intent", kind=kind, payload_fingerprint=DIGEST, checkpoint=checkpoint)


def dispatched(state=None, clock=None):
    state, clock = state or initial(), clock or FrozenClock(AT)
    grant = claim(
        state,
        token=TOKEN,
        worker_id="worker",
        clock=clock,
        ttl=timedelta(seconds=60),
        evidence=proof(state, clock),
        expected_revision=state.revision,
    )
    result = begin_dispatch(
        grant.state,
        token=TOKEN,
        fence=grant.state.fence,
        clock=clock,
        expected_revision=grant.state.revision,
        evidence=proof(grant.state, clock, "dispatch"),
    )
    return result, clock


def receipt(state, *, delivered=True, evidence_ref=None):
    card = "card" if delivered and state.intent.kind == "create" else state.card_id
    message = "message" if delivered and state.intent.kind == "send" else state.message_id
    return StreamReceipt(
        state.scope,
        state.intent.operation_id,
        state.intent.payload_fingerprint,
        state.intent.sequence,
        card,
        message,
        evidence_ref,
    )


def ack(state, clock):
    return acknowledge(
        state, receipt(state), token=TOKEN, fence=state.fence, expected_revision=state.revision, clock=clock
    )


def test_full_lifecycle_keeps_one_card_and_monotonic_sequence():
    state, clock = dispatched()
    state = ack(state, clock)
    assert state.card_id == "card" and state.message_id is None
    for index, kind in enumerate(("send", "update", "close")):
        state = next_intent(
            state, operation_id=f"next-{index}", kind=kind, payload_fingerprint=DIGEST, expected_revision=state.revision
        )
        state, _ = dispatched(state, clock)
        state = ack(state, clock)
    assert state.card_id == "card" and state.message_id == "message"
    assert state.last_acked_sequence == state.last_reserved_sequence == 2
    with pytest.raises(StreamError):
        next_intent(
            state, operation_id="again", kind="create", payload_fingerprint=DIGEST, expected_revision=state.revision
        )


def test_claim_and_dispatch_need_separate_current_transaction_evidence():
    state, clock = initial(), FrozenClock(AT)
    evidence = proof(state, clock)
    grant = claim(
        state,
        token=TOKEN,
        worker_id="worker",
        clock=clock,
        ttl=timedelta(seconds=60),
        evidence=evidence,
        expected_revision=0,
    )
    with pytest.raises(StreamError):
        begin_dispatch(grant.state, token=TOKEN, fence=1, expected_revision=1, clock=clock, evidence=evidence)
    with pytest.raises(StreamError):
        claim(
            state,
            token=TOKEN,
            worker_id="worker",
            clock=clock,
            ttl=timedelta(seconds=60),
            evidence=True,
            expected_revision=0,
        )


@pytest.mark.parametrize("change", ["epoch", "source", "dependency", "parse_only", "subject", "answer", "run"])
def test_complete_freshness_and_scope_remain_required(change):
    state, clock = initial(), FrozenClock(AT)
    body = envelope()
    evidence = proof(state, clock)
    if change == "epoch":
        evidence = replace(evidence, current_source_epoch=2)
    elif change in {"source", "dependency"}:
        index = 0 if change == "source" else 1
        versions = list(evidence.versions)
        versions[index] = replace(versions[index], current_hash="0" * 64)
        evidence = replace(evidence, versions=tuple(versions))
    else:
        if change == "parse_only":
            body.pop("validation")
        elif change == "subject":
            body["meta"]["subject_id"] = "other"
        elif change == "answer":
            body["answer"] = "不同正文"
        else:
            body["meta"]["core_run"]["run_id"] = "other"
        evidence = replace(evidence, validated_payload=body, run_payload_fingerprint=fingerprint(body))
    with pytest.raises(StreamError):
        claim(
            state,
            token=TOKEN,
            worker_id="worker",
            clock=clock,
            ttl=timedelta(seconds=60),
            evidence=evidence,
            expected_revision=0,
        )


def test_undispatched_expiry_reclaims_with_new_fence_but_stale_worker_cannot_send():
    state, clock = initial(), FrozenClock(AT)
    first = claim(
        state,
        token=TOKEN,
        worker_id="worker",
        clock=clock,
        ttl=timedelta(seconds=1),
        evidence=proof(state, clock),
        expected_revision=0,
    ).state
    clock.advance(timedelta(seconds=1))
    second = claim(
        first,
        token="new-synthetic-token",
        worker_id="new-worker",
        clock=clock,
        ttl=timedelta(seconds=60),
        evidence=proof(first, clock),
        expected_revision=1,
    ).state
    assert second.fence == 2
    with pytest.raises(StreamError):
        begin_dispatch(
            second,
            token=TOKEN,
            fence=1,
            expected_revision=second.revision,
            clock=clock,
            evidence=proof(second, clock, "dispatch"),
        )


def test_dispatched_expiry_and_restore_are_uncertain_and_never_retry_automatically():
    state, clock = dispatched()
    restored = restore_state(state_metadata(state), scope=SCOPE)
    assert restored.phase == "uncertain"
    clock.advance(timedelta(seconds=60))
    unknown = recover_expired(state, expected_revision=state.revision, clock=clock)
    assert unknown.phase == "uncertain" and fallback_intent(unknown) is None
    with pytest.raises(StreamError):
        claim(
            unknown,
            token=TOKEN,
            worker_id="worker",
            clock=clock,
            ttl=timedelta(seconds=60),
            evidence=proof(unknown, clock),
            expected_revision=unknown.revision,
        )


def test_only_confirmed_close_refusal_can_produce_fallback():
    state, clock = dispatched(initial("close"))
    unknown = mark_uncertain(state, token=TOKEN, fence=state.fence, expected_revision=state.revision, clock=clock)
    assert fallback_intent(unknown) is None
    refused = reconcile(
        unknown,
        receipt(unknown, delivered=False, evidence_ref="verified-unsent"),
        delivered=False,
        expected_revision=unknown.revision,
    )
    assert fallback_intent(refused).kind == "fallback"
    other, clock = dispatched()
    rejected = reject(
        other,
        receipt(other, delivered=False, evidence_ref="verified-refusal"),
        token=TOKEN,
        fence=other.fence,
        expected_revision=other.revision,
        clock=clock,
    )
    assert fallback_intent(rejected) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", replace(SCOPE, target="ou_foreign")),
        ("operation_id", "other"),
        ("payload_fingerprint", "0" * 64),
        ("sequence", 99),
        ("card_id", "other-card"),
        ("message_id", "other-message"),
    ],
)
def test_receipts_cannot_change_any_reserved_binding(field, value):
    state, clock = dispatched(initial("update"))
    with pytest.raises(StreamError):
        acknowledge(
            state,
            replace(receipt(state), **{field: value}),
            token=TOKEN,
            fence=state.fence,
            expected_revision=state.revision,
            clock=clock,
        )


def test_metadata_contains_no_body_token_or_payload_and_preserves_scope():
    state, _ = dispatched()
    encoded = state_metadata(state)
    raw = json.dumps(encoded)
    assert TOKEN not in raw and "合成最终正文" not in raw and "ou_synthetic" not in raw
    with pytest.raises(StreamError):
        restore_state(encoded, scope=replace(SCOPE, run_id="other-run"))


def test_one_thousand_frozen_clock_lease_and_unknown_properties():
    rng = random.Random(20261022)
    for _ in range(1000):
        state, clock = initial(), FrozenClock(AT)
        ttl = timedelta(milliseconds=rng.randrange(1, 10000))
        grant = claim(
            state,
            token=TOKEN,
            worker_id="worker",
            clock=clock,
            ttl=ttl,
            evidence=proof(state, clock),
            expected_revision=0,
        )
        leased = grant.state
        if rng.choice((True, False)):
            leased = begin_dispatch(
                leased,
                token=TOKEN,
                fence=leased.fence,
                expected_revision=leased.revision,
                clock=clock,
                evidence=proof(leased, clock, "dispatch"),
            )
        clock.advance(ttl)
        result = recover_expired(leased, expected_revision=leased.revision, clock=clock)
        assert result.phase == ("uncertain" if leased.phase == "dispatched" else "prepared")
        assert result.revision > leased.revision and result.fence == leased.fence
        assert result.lease is None and fallback_intent(result) is None


def test_manifest_omission_duplicate_and_extra_version_fail_closed():
    state, clock = initial(), FrozenClock(AT)
    evidence = proof(state, clock)
    for values in (evidence.versions[:1], (*evidence.versions, evidence.versions[0])):
        with pytest.raises(StreamError):
            replace(evidence, versions=values)
    with pytest.raises(StreamError):
        replace(evidence, expected_manifest=(*evidence.expected_manifest, ("source", "missing-source", DIGEST)))


def test_renewal_requires_live_capability_and_extends_expiry():
    state, clock = initial(), FrozenClock(AT)
    leased = claim(
        state,
        token=TOKEN,
        worker_id="worker",
        clock=clock,
        ttl=timedelta(seconds=1),
        evidence=proof(state, clock),
        expected_revision=0,
    ).state
    extended = renew(leased, token=TOKEN, fence=1, expected_revision=1, clock=clock, ttl=timedelta(seconds=2))
    assert extended.lease.expires_at == AT + timedelta(seconds=2)
    with pytest.raises(StreamError):
        renew(
            extended,
            token=TOKEN,
            fence=True,
            expected_revision=extended.revision,
            clock=clock,
            ttl=timedelta(seconds=3),
        )

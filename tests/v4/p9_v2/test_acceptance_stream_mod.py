"""Independent full-payload/source evidence at both claim and dispatch boundaries."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import (
    FreshnessEvidence,
    StreamError,
    StreamReceipt,
    StreamScope,
    VersionEvidence,
    acknowledge,
    begin_dispatch,
    claim,
    prepare_intent,
)
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = StreamScope("owner", "self", "outbox", "run", "business", "feishu", "ou_synthetic")
TTL = timedelta(seconds=60)


def payload():
    return {
        "schema": "core4.0",
        "message_id": "message",
        "text": "SYNTHETIC_PRIVATE_BODY",
        "receipts": [],
        "used_fact_ids": [],
        "used_claim_ids": [],
        "asked": None,
        "options": None,
        "review": {"state": "passed", "reasons": []},
        "usage": {"offline": True},
        "validation": {"status": "validated", "valid": True, "schema": "core4.0"},
        "meta": {
            "core_run": {"run_id": "run", "operation_id": "run-operation"},
            "subject_id": "self",
            "case_ids": [],
            "structural_warnings": [],
        },
    }


def proof(state, purpose, clock):
    versions = (
        VersionEvidence("source", "source-one", "a" * 64, "a" * 64),
        VersionEvidence("dependency", "dependency-one", "b" * 64, "b" * 64),
    )
    body = payload()
    return FreshnessEvidence(
        scope=state.scope,
        operation_id=state.intent.operation_id,
        expected_revision=state.revision,
        purpose=purpose,
        checked_at=clock.now(),
        transaction_id="synthetic-transaction-" + purpose,
        run_status="succeeded",
        intent_payload_fingerprint=state.intent.payload_fingerprint,
        run_payload_fingerprint=fingerprint(body),
        validated_payload=body,
        versions=versions,
        expected_source_epoch=7,
        current_source_epoch=7,
        expected_manifest=tuple((v.category, v.identity, v.expected_hash) for v in versions),
    )


def prepared():
    return prepare_intent(SCOPE, operation_id="create-one", kind="create", payload_fingerprint="c" * 64)


def leased(state, clock, token="synthetic-secret-token"):
    return claim(
        state,
        token=token,
        worker_id="worker",
        clock=clock,
        ttl=TTL,
        evidence=proof(state, "claim", clock),
        expected_revision=state.revision,
    )


def dispatched(state, clock, token="synthetic-secret-token"):
    grant = leased(state, clock, token)
    state = begin_dispatch(
        grant.state,
        token=token,
        fence=grant.state.fence,
        expected_revision=grant.state.revision,
        clock=clock,
        evidence=proof(grant.state, "dispatch", clock),
    )
    return state, grant


def receipt(state, **changes):
    values = dict(
        scope=state.scope,
        operation_id=state.intent.operation_id,
        payload_fingerprint=state.intent.payload_fingerprint,
        sequence=state.intent.sequence,
        card_id="card-one" if state.intent.kind == "create" else state.card_id,
        message_id="remote-message" if state.intent.kind == "send" else state.message_id,
        evidence_ref="synthetic-bound-proof",
    )
    values.update(changes)
    return StreamReceipt(**values)


def complete(state, clock):
    state, grant = dispatched(state, clock)
    return acknowledge(
        state, receipt(state), token=grant.token, fence=state.fence, expected_revision=state.revision, clock=clock
    )


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
@pytest.mark.parametrize(
    "change",
    [
        "run_status",
        "wrong_scope",
        "revision",
        "purpose",
        "time",
        "operation",
        "intent_payload",
        "run_payload",
        "source_epoch",
        "revoked",
        "inactive",
        "changed_hash",
        "missing_manifest_entry",
    ],
)
def test_stale_or_incomplete_evidence_cannot_authorize_claim_or_sending(boundary, change):
    clock = FrozenClock(AT)
    state = prepared() if boundary == "claim" else leased(prepared(), clock).state
    valid = proof(state, boundary, clock)
    with pytest.raises(StreamError):
        bad = changed_proof(valid, change)
        if boundary == "claim":
            claim(
                state,
                token="token",
                worker_id="worker",
                clock=clock,
                ttl=TTL,
                evidence=bad,
                expected_revision=state.revision,
            )
        else:
            begin_dispatch(
                state,
                token="synthetic-secret-token",
                fence=state.fence,
                expected_revision=state.revision,
                clock=clock,
                evidence=bad,
            )


def changed_proof(value, change):
    fields = {
        "run_status": {"run_status": "running"},
        "wrong_scope": {"scope": replace(SCOPE, owner_id="other")},
        "revision": {"expected_revision": value.expected_revision + 1},
        "purpose": {"purpose": "dispatch" if value.purpose == "claim" else "claim"},
        "time": {"checked_at": value.checked_at - timedelta(microseconds=1)},
        "operation": {"operation_id": "another"},
        "intent_payload": {"intent_payload_fingerprint": "d" * 64},
        "run_payload": {"run_payload_fingerprint": "d" * 64},
        "source_epoch": {"current_source_epoch": 8},
    }
    if change in fields:
        return replace(value, **fields[change])
    first, second = value.versions
    if change == "revoked":
        return replace(value, versions=(replace(first, revoked=True), second))
    if change == "inactive":
        return replace(value, versions=(replace(first, active=False), second))
    if change == "changed_hash":
        return replace(value, versions=(replace(first, current_hash="d" * 64), second))
    return replace(value, versions=(first,))


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
@pytest.mark.parametrize(
    "change", ["just_boolean", "missing_validation", "missing_meta", "wrong_run", "wrong_subject", "bad_receipt"]
)
def test_complete_payload_validation_is_required_not_only_a_host_success_boolean(boundary, change):
    clock = FrozenClock(AT)
    state = prepared() if boundary == "claim" else leased(prepared(), clock).state
    body = payload()
    if change == "just_boolean":
        body = {"validation": {"valid": True}, "text": "SYNTHETIC_PRIVATE_BODY"}
    elif change == "missing_validation":
        body.pop("validation")
    elif change == "missing_meta":
        body.pop("meta")
    elif change == "wrong_run":
        body["meta"]["core_run"]["run_id"] = "other"
    elif change == "wrong_subject":
        body["meta"]["subject_id"] = "other"
    else:
        body["receipts"] = [{"private_unvalidated": "SYNTHETIC_PRIVATE_BODY"}]
    evidence = replace(proof(state, boundary, clock), validated_payload=body, run_payload_fingerprint=fingerprint(body))
    with pytest.raises(StreamError) as caught:
        if boundary == "claim":
            claim(
                state,
                token="token",
                worker_id="worker",
                clock=clock,
                ttl=TTL,
                evidence=evidence,
                expected_revision=state.revision,
            )
        else:
            begin_dispatch(
                state,
                token="synthetic-secret-token",
                fence=state.fence,
                expected_revision=state.revision,
                clock=clock,
                evidence=evidence,
            )
    assert "SYNTHETIC_PRIVATE_BODY" not in str(caught.value)


def test_claim_proof_cannot_be_reused_as_dispatch_proof_and_payload_is_deeply_frozen():
    clock, state = FrozenClock(AT), prepared()
    evidence = proof(state, "claim", clock)
    grant = claim(
        state,
        token="token",
        worker_id="worker",
        clock=clock,
        ttl=TTL,
        evidence=evidence,
        expected_revision=state.revision,
    )
    with pytest.raises(StreamError):
        begin_dispatch(
            grant.state,
            token="token",
            fence=grant.state.fence,
            expected_revision=grant.state.revision,
            clock=clock,
            evidence=evidence,
        )
    original = copy.deepcopy(payload())
    assert evidence.validated_payload["text"] == original["text"]
    with pytest.raises(TypeError):
        evidence.validated_payload["meta"]["subject_id"] = "other"

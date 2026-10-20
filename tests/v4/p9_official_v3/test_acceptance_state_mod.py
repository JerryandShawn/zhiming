"""Independent close/recovery/source boundaries from frozen document-26 expectations."""

from dataclasses import replace
from datetime import timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_official_v3 import (
    OfficialAck,
    OfficialOutcome,
    OfficialState,
    begin_dispatch,
    claim,
    reconcile,
    restore_state,
    settle_outcome,
    state_metadata,
    stream_deadline_action,
)

from .support_mod import (
    TOKEN,
    Environment,
    acknowledge,
    dispatch,
    environment,
    freshness,
    open_stream,
    prepare,
    run_step,
)


def refusal(
    state: OfficialState, env: Environment, status: str, *, reason: str = "synthetic_refusal", after_ms: int = 0
) -> OfficialState:
    assert state.lease_state is not None
    return settle_outcome(
        state,
        OfficialOutcome(status, reason, after_ms),
        evidence_ref="synthetic-outcome-evidence",
        token=TOKEN,
        fence=state.lease_state.fence,
        clock=env.clock,
        expected_revision=state.revision,
    )


def test_only_two_independent_acknowledgements_close_the_stream() -> None:
    env = environment()
    state = open_stream(env)
    with pytest.raises(ValueError):
        prepare(state, env, "close_streaming")
    final_pending = prepare(state, env, "finalize", env.artifact.final_card)
    assert not final_pending.state.finalize_acked and not final_pending.state.close_acked
    assert final_pending.state.phase != "closed"
    state = acknowledge(dispatch(final_pending, env), env)
    assert state.finalize_acked and not state.close_acked and state.phase != "closed"
    closing = prepare(state, env, "close_streaming")
    assert closing.request.sequence == final_pending.request.sequence + 1
    assert closing.request.operation_id != final_pending.request.operation_id
    assert closing.request.wire_uuid != final_pending.request.wire_uuid
    state = acknowledge(dispatch(closing, env), env)
    assert state.finalize_acked and state.close_acked and state.phase == "closed"


@pytest.mark.parametrize("kind", ["finalize", "close_streaming"])
@pytest.mark.parametrize("outcome", ["rejected", "retryable", "uncertain"])
def test_each_close_step_has_its_own_non_ack_path(kind: str, outcome: str) -> None:
    env = environment()
    state = open_stream(env)
    if kind == "close_streaming":
        state = run_step(state, env, "finalize", env.artifact.final_card)
    payload = env.artifact.final_card if kind == "finalize" else None
    after_ms = 1000 if outcome == "retryable" else 0
    state = refusal(dispatch(prepare(state, env, kind, payload), env), env, outcome, after_ms=after_ms)
    assert not state.close_acked and state.phase != "closed"
    assert state.finalize_acked is (kind == "close_streaming")
    if outcome == "uncertain":
        with pytest.raises(ValueError):
            prepare(state, env, kind, payload)
    if kind == "finalize" and outcome == "rejected":
        # Public API calls the specification's fallback intent "fallback_pending".
        assert state.stage == "fallback_pending"
    if kind == "close_streaming":
        assert state.stage != "fallback_intent"
    restored = restore_state(state_metadata(state), scope=env.scope)
    assert restored == state


def test_close_rejection_gets_one_new_sequence_retry_without_plaintext_fallback() -> None:
    env = environment()
    state = run_step(open_stream(env), env, "finalize", env.artifact.final_card)
    first = prepare(state, env, "close_streaming")
    state = refusal(dispatch(first, env), env, "rejected")
    env.clock.advance(timedelta(seconds=1))
    second = prepare(state, env, "close_streaming")
    assert second.request.sequence > first.request.sequence
    assert second.request.wire_uuid != first.request.wire_uuid
    state = refusal(dispatch(second, env), env, "rejected")
    assert not state.close_acked and state.finalize_acked and state.phase != "closed"
    assert state.stage != "fallback_intent"
    # The terminal failure is a stage, while retry_reason retains the last refusal.
    assert state.stage == "streaming_close_failed"
    with pytest.raises(ValueError):
        prepare(state, env, "close_streaming")


@pytest.mark.parametrize("kind", ["create", "send", "update", "finalize", "close_streaming"])
def test_unknown_snapshots_keep_operation_identity_and_never_prepare_resend(kind: str) -> None:
    env = environment()
    if kind == "create":
        from mingjing_core.adapters.channels.cardkit_official_v3 import new_state

        state = new_state(env.scope)
    elif kind == "send":
        from mingjing_core.adapters.channels.cardkit_official_v3 import new_state

        state = run_step(new_state(env.scope), env, "create")
    else:
        state = open_stream(env)
    if kind == "close_streaming":
        state = run_step(state, env, "finalize", env.artifact.final_card)
    payload = env.artifact.final_card if kind == "finalize" else None
    if kind == "update":
        payload = env.payload["text"]
    prepared = prepare(state, env, kind, payload)
    state = refusal(dispatch(prepared, env), env, "uncertain")
    restored = restore_state(state_metadata(state), scope=env.scope)
    assert restored.operation.operation_id == prepared.request.operation_id
    assert restored.operation.wire_uuid == prepared.request.wire_uuid
    assert restored.operation.sequence == prepared.request.sequence
    assert restored.phase == "uncertain"
    with pytest.raises(ValueError):
        prepare(restored, env, kind, payload)


def test_reconcile_close_unknown_confirms_same_operation_without_new_request() -> None:
    env = environment()
    state = run_step(open_stream(env), env, "finalize", env.artifact.final_card)
    closing = prepare(state, env, "close_streaming")
    unknown = refusal(dispatch(closing, env), env, "uncertain")
    confirmed = reconcile(
        unknown,
        OfficialAck("12345", "om_syntheticMessage", closing.request.sequence),
        delivered=True,
        evidence_ref="synthetic-platform-lookup",
        clock=env.clock,
        expected_revision=unknown.revision,
    )
    assert confirmed.phase == "closed" and confirmed.close_acked
    assert confirmed.operation.operation_id == closing.request.operation_id
    assert confirmed.operation.wire_uuid == closing.request.wire_uuid


@pytest.mark.parametrize("stage", ["claim", "dispatch"])
@pytest.mark.parametrize("mutation", ["source_revoked", "source_inactive", "source_revision", "epoch", "run_status"])
def test_new_protocol_cannot_bypass_current_source_recheck(stage: str, mutation: str) -> None:
    env = environment()
    prepared = prepare(open_stream(env), env, "finalize", env.artifact.final_card)
    state = prepared.state
    if stage == "dispatch":
        state = claim(
            state,
            prepared.request,
            artifact=env.artifact,
            evidence=freshness(state, env, "claim"),
            token=TOKEN,
            worker_id="worker-mod",
            clock=env.clock,
            ttl=timedelta(seconds=30),
            expected_revision=state.revision,
        )
    evidence = freshness(state, env, stage)
    first = evidence.versions[0]
    changes = {
        "source_revoked": {"revoked": True},
        "source_inactive": {"active": False},
        "source_revision": {"current_hash": "c" * 64},
    }
    if mutation in changes:
        evidence = replace(evidence, versions=(replace(first, **changes[mutation]), evidence.versions[1]))
    elif mutation == "epoch":
        evidence = replace(evidence, current_source_epoch=8)
    else:
        evidence = replace(evidence, run_status="failed")
    args = {
        "artifact": env.artifact,
        "evidence": evidence,
        "token": TOKEN,
        "clock": env.clock,
        "expected_revision": state.revision,
    }
    with pytest.raises(ValueError):
        if stage == "claim":
            claim(state, prepared.request, worker_id="worker-mod", ttl=timedelta(seconds=30), **args)
        else:
            begin_dispatch(state, prepared.request, fence=state.lease_state.fence, **args)


@pytest.mark.parametrize("field", ["owner_id", "subject_id", "run_id", "outbox_id", "target"])
def test_restore_is_bound_to_complete_owner_and_destination_scope(field: str) -> None:
    env = environment()
    scope = replace(env.scope, **{field: "synthetic-other"})
    with pytest.raises(ValueError):
        restore_state(state_metadata(open_stream(env)), scope=scope)


@pytest.mark.parametrize("field", ["method", "path", "body", "sequence"])
def test_wire_request_cannot_change_between_prepare_and_claim(field: str) -> None:
    env = environment()
    prepared = prepare(open_stream(env), env, "finalize", env.artifact.final_card)
    changed = {
        "method": "DELETE",
        "path": "/synthetic/foreign/card",
        "body": {"private": "synthetic"},
        "sequence": prepared.request.sequence + 1,
    }[field]
    with pytest.raises(ValueError):
        request = replace(prepared.request, **{field: changed})
        claim(
            prepared.state,
            request,
            artifact=env.artifact,
            evidence=freshness(prepared.state, env, "claim"),
            token=TOKEN,
            worker_id="worker-mod",
            clock=env.clock,
            ttl=timedelta(seconds=30),
            expected_revision=prepared.state.revision,
        )


def test_ten_minute_timeout_returns_host_intent_and_no_automatic_new_card() -> None:
    env = environment()
    state = open_stream(env)
    env.clock.advance(timedelta(minutes=10))
    result = stream_deadline_action(state, clock=env.clock)
    assert "create" not in str(result).lower() and "send" not in str(result).lower()
    assert state.card_id == "12345" and state.message_id == "om_syntheticMessage"

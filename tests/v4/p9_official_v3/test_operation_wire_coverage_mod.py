"""Stable operation replay, backoff and bound wire payloads are independent delivery guards."""

from dataclasses import replace
from datetime import timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_official_v3 import (
    OfficialError,
    OfficialOutcome,
    OfficialPolicy,
    build_wire_request,
    new_state,
    prepare_operation,
    restore_state,
    settle_outcome,
    state_metadata,
    stream_deadline_action,
)
from mingjing_core.streaming.json_values import thaw_json

from .isolated_coverage_mod import isolated_p9 as isolated_p9
from .support_mod import TEXT, TOKEN, acknowledge, dispatch, environment, open_stream, prepare, run_step


@pytest.mark.parametrize("scope", [None, "raw-scope"])
def test_untyped_scope_cannot_create_an_official_state(scope: object) -> None:
    with pytest.raises(OfficialError):
        new_state(scope)


def test_web_channel_is_not_a_feishu_outbox_and_foreign_artifact_cannot_prepare_an_operation() -> None:
    env = environment()
    with pytest.raises(OfficialError):
        new_state(replace(env.scope, channel="web"))
    with pytest.raises(OfficialError):
        prepare_operation(
            new_state(env.scope),
            "create",
            operation_id="synthetic-foreign-artifact",
            artifact=replace(env.artifact, scope=replace(env.scope, owner_id="other")),
            clock=env.clock,
        )


@pytest.mark.parametrize("phase", ["prepared", "dispatched", "restored_unknown", "acked"])
def test_exact_operation_replay_never_returns_a_second_request_or_reserves_sequence(phase: str) -> None:
    env = environment()
    prepared = prepare(open_stream(env), env, "update", TEXT[:3])
    state = prepared.state
    if phase != "prepared":
        state = dispatch(prepared, env)
        if phase == "restored_unknown":
            state = restore_state(state_metadata(state), scope=env.scope)
        elif phase == "acked":
            state = acknowledge(state, env)
    replay = prepare_operation(
        state, "update", TEXT[:3], operation_id=prepared.request.operation_id, artifact=env.artifact, clock=env.clock
    )
    assert replay.status == "replayed" and replay.request is None and replay.state is state
    assert replay.state.last_reserved_sequence == prepared.request.sequence
    with pytest.raises(OfficialError) as caught:
        prepare_operation(
            state,
            "update",
            TEXT[:4],
            operation_id=prepared.request.operation_id,
            artifact=env.artifact,
            clock=env.clock,
        )
    assert caught.value.reason_code == "operation_payload_changed"


def test_same_operation_id_cannot_change_wire_kind_even_with_the_same_authorized_artifact() -> None:
    env = environment()
    prepared = prepare(open_stream(env), env, "update", TEXT[:3])
    with pytest.raises(OfficialError) as caught:
        prepare_operation(
            prepared.state,
            "finalize",
            env.artifact.final_card,
            operation_id=prepared.request.operation_id,
            artifact=env.artifact,
            clock=env.clock,
        )
    assert caught.value.reason_code == "operation_payload_changed"


def test_retry_waits_until_exact_not_before_and_does_not_consume_a_sequence_while_deferred() -> None:
    env = environment()
    sent = dispatch(prepare(open_stream(env), env, "update", TEXT[:3]), env)
    refused = settle_outcome(
        sent,
        OfficialOutcome("retryable", "rate_limited", 2300),
        evidence_ref="synthetic-rate-evidence",
        token=TOKEN,
        fence=sent.lease_state.fence,
        clock=env.clock,
        expected_revision=sent.revision,
    )
    env.clock.advance(timedelta(milliseconds=2299, microseconds=999))
    with pytest.raises(OfficialError) as caught:
        prepare(refused, env, "update", TEXT[:3])
    assert caught.value.reason_code == "retry_not_due"
    env.clock.advance(timedelta(microseconds=1))
    retry = prepare(refused, env, "update", TEXT[:3])
    assert retry.request is not None and retry.request.sequence == refused.last_reserved_sequence + 1


@pytest.mark.parametrize("interval", [300, 400, 500])
def test_card_throttle_uses_exact_owner_clock_interval_and_never_the_host_zone(interval: int) -> None:
    env = environment()
    state = open_stream(env)
    state = replace(state, policy=OfficialPolicy(interval))
    env.clock.advance(state.last_attempt_at + timedelta(milliseconds=interval, microseconds=-1) - env.clock.now())
    with pytest.raises(OfficialError) as caught:
        prepare(state, env, "update", TEXT[:3])
    assert caught.value.reason_code == "cardkit_throttled"
    env.clock.advance(timedelta(microseconds=1))
    assert prepare(state, env, "update", TEXT[:3]).request is not None


def test_clock_regression_and_operation_before_card_creation_cannot_describe_a_request() -> None:
    env = environment()
    with pytest.raises(OfficialError) as caught:
        prepare(new_state(env.scope), env, "update", TEXT[:3])
    assert caught.value.reason_code == "operation_stage_invalid"
    state = open_stream(env)
    env.clock.advance(state.last_attempt_at - timedelta(microseconds=1) - env.clock.now())
    with pytest.raises(OfficialError) as caught:
        prepare(state, env, "update", TEXT[:3])
    assert caught.value.reason_code == "clock_went_backwards"


def test_changed_content_cannot_reuse_a_rejected_sequence_when_gaps_are_disabled() -> None:
    env = environment()
    state = replace(open_stream(env), policy=OfficialPolicy(allow_sequence_gaps=False))
    sent = dispatch(prepare(state, env, "update", TEXT[:3]), env)
    refused = settle_outcome(
        sent,
        OfficialOutcome("retryable", "rate_limited", 400),
        evidence_ref="synthetic-rate-evidence",
        token=TOKEN,
        fence=sent.lease_state.fence,
        clock=env.clock,
        expected_revision=sent.revision,
    )
    env.clock.advance(timedelta(milliseconds=400))
    same = prepare(refused, env, "update", TEXT[:3])
    changed = prepare(refused, env, "update", TEXT[:4])
    assert same.request.sequence == refused.last_reserved_sequence
    assert changed.request.sequence == refused.last_reserved_sequence + 1


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("create", {"schema": "synthetic-unapproved-initial"}),
        ("send", "unapproved content"),
        ("update", []),
        ("update", "x" * 100001),
        ("close_streaming", {"streaming_mode": True}),
        ("unknown", None),
    ],
    ids=["initial-override", "send-override", "update-type", "update-length", "settings-override", "unknown-kind"],
)
def test_wire_request_derives_structural_payloads_and_refuses_unapproved_override(kind: str, payload: object) -> None:
    env = environment()
    state = open_stream(env)
    with pytest.raises(ValueError):
        build_wire_request(
            state, kind, payload, operation_id="synthetic-wire-override", sequence=1, artifact=env.artifact
        )


def test_finalize_card_override_and_utf8_wire_budget_cannot_escape_the_bound_approved_artifact() -> None:
    env = environment()
    state = open_stream(env)
    card = thaw_json(env.artifact.final_card)
    card["body"]["elements"][0]["content"] = "synthetic-unapproved-final"
    with pytest.raises(OfficialError) as caught:
        prepare(state, env, "finalize", card)
    assert caught.value.reason_code == "final_card_not_authorized_artifact"
    with pytest.raises(OfficialError) as caught:
        build_wire_request(
            state, "update", "汉" * 12000, operation_id="synthetic-wire-too-large", sequence=1, artifact=env.artifact
        )
    assert caught.value.reason_code == "wire_body_invalid_or_too_large"


def test_no_started_stream_has_no_deadline_action_and_final_ack_alone_does_not_close() -> None:
    env = environment()
    assert stream_deadline_action(new_state(env.scope), clock=env.clock) is None
    state = run_step(open_stream(env), env, "finalize", env.artifact.final_card)
    assert state.finalize_acked and not state.close_acked
    env.clock.advance(timedelta(minutes=10))
    assert stream_deadline_action(state, clock=env.clock) == "reopen_or_finalize"
    assert state.card_id == "12345" and state.message_id == "om_syntheticMessage"

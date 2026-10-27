"""Independent migration/restore cases preserve legacy proof and reject lifecycle rollback."""

import copy
from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_checkpoint import snapshot
from mingjing_core.adapters.channels.cardkit_contracts import PendingOperation
from mingjing_core.adapters.channels.cardkit_official_v3 import (
    OfficialError,
    OfficialOutcome,
    claim,
    merge_official_reconciliation,
    new_state,
    prepare_operation,
    restore_state,
    settle_outcome,
    state_metadata,
)
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import namespace_fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import restore_state as restore_lease
from mingjing_core.adapters.channels.stream_outbox_v2 import state_metadata as lease_metadata

from .isolated_coverage_mod import isolated_p9 as isolated_p9
from .namespace_support_coverage_mod import binding, legacy_container, merge, old_checkpoint
from .support_mod import TEXT, TOKEN, acknowledge, dispatch, environment, freshness, open_stream, prepare, run_step


@pytest.mark.parametrize("mode", ["stream", "checkpoint", "both"])
def test_installing_official_child_preserves_complete_legacy_evidence_and_unrecognized_siblings(mode: str) -> None:
    env = environment()
    state = open_stream(env)
    value = legacy_container(env, state, mode)
    original = copy.deepcopy(value)
    installed = merge(value, state, env)
    saved = installed.as_dict()
    assert value == original and installed.changed and installed.next_row_revision == 8
    for key, prior in original["cardkit"].items():
        if key != "revision":
            assert saved["cardkit"][key] == prior
    assert saved["old_delivery_proof"] == original["old_delivery_proof"]
    assert saved["cardkit"]["revision"] == original["cardkit"]["revision"] + 1
    saved["cardkit"]["unknown_vendor_child"]["flags"].append(999)
    assert installed.as_dict()["cardkit"]["unknown_vendor_child"]["flags"] == [1, 2]


@pytest.mark.parametrize("phase", ["prepared", "leased"])
@pytest.mark.parametrize("elapsed", [timedelta(0), timedelta(seconds=61)])
@pytest.mark.parametrize("same_operation", [False, True])
def test_unsettled_legacy_intent_cannot_gain_a_parallel_official_operation_even_after_lease_expiry(
    phase: str, elapsed: timedelta, same_operation: bool
) -> None:
    env = environment()
    prior = prepare(new_state(env.scope), env, "create")
    legacy = prior.state
    if phase == "leased":
        legacy = claim(
            legacy,
            prior.request,
            artifact=env.artifact,
            evidence=freshness(legacy, env, "claim"),
            token=TOKEN,
            worker_id="synthetic-legacy-worker",
            clock=env.clock,
            ttl=timedelta(seconds=30),
            expected_revision=legacy.revision,
        )
    env.clock.advance(elapsed)
    operation_id = legacy.operation.operation_id if same_operation else "different-official-create"
    candidate = prepare_operation(
        new_state(env.scope), "create", operation_id=operation_id, artifact=env.artifact, clock=env.clock
    ).state
    candidate = replace(candidate, lease_state=replace(candidate.lease_state, fence=legacy.lease_state.fence))
    assert (candidate.operation.operation_id == legacy.operation.operation_id) is same_operation
    value = legacy_container(env, legacy, "stream")
    original = copy.deepcopy(value)
    with pytest.raises(OfficialError) as caught:
        merge(value, candidate, env)
    assert caught.value.reason_code == "legacy_pending_requires_explicit_migration"
    assert value == original


@pytest.mark.parametrize("phase", ["dispatched", "uncertain"])
def test_unresolved_legacy_stream_cannot_be_silently_upgraded_into_a_second_sender(phase: str) -> None:
    env = environment()
    prior = open_stream(env)
    active = dispatch(prepare(prior, env, "update", TEXT[:3]), env)
    value = legacy_container(env, prior, "stream")
    value["cardkit"]["stream"] = lease_metadata(active.lease_state)
    if phase == "uncertain":
        value["cardkit"]["stream"] = lease_metadata(restore_lease(value["cardkit"]["stream"], scope=env.scope))
    original = copy.deepcopy(value)
    with pytest.raises(OfficialError, match="卡片协议") as caught:
        merge(value, active, env)
    assert caught.value.reason_code == "legacy_unknown_requires_reconciliation"
    assert value == original


@pytest.mark.parametrize("phase", ["in_flight", "uncertain"])
def test_old_pending_checkpoint_does_not_become_permission_to_publish_a_new_official_effect(phase: str) -> None:
    env = environment()
    state = run_step(open_stream(env), env, "update", TEXT[:3])
    old = replace(
        old_checkpoint(state),
        phase=phase,
        pending=PendingOperation(
            "update", "synthetic-unresolved-legacy-effect", state.artifact_fingerprint, state.last_reserved_sequence, 0
        ),
    )
    value = legacy_container(env, state, "checkpoint")
    value["cardkit"]["checkpoint"] = snapshot(old)
    with pytest.raises(OfficialError) as caught:
        merge(value, state, env)
    assert caught.value.reason_code == "legacy_unknown_requires_reconciliation"


@pytest.mark.parametrize("field", ["card_id", "message_id"])
@pytest.mark.parametrize("kind", ["stream", "checkpoint"])
def test_legacy_remote_identity_cannot_be_rebound_by_a_current_owner_cas(field: str, kind: str) -> None:
    env = environment()
    state = open_stream(env)
    value = legacy_container(env, state, kind)
    target = value["cardkit"][kind]
    if kind == "checkpoint":
        target = target["checkpoint"]
    target[field] = "67890" if field == "card_id" else "om_otherSynthetic"
    with pytest.raises(OfficialError) as caught:
        merge(value, state, env)
    assert caught.value.reason_code == "legacy_remote_identity_changed"


@pytest.mark.parametrize("field", ["last_reserved_sequence", "last_acked_sequence", "fence"])
def test_legacy_sequence_ack_or_fence_cannot_regress_during_namespace_installation(field: str) -> None:
    env = environment()
    older = open_stream(env)
    current = run_step(older, env, "update", TEXT[:3])
    value = legacy_container(env, current, "stream")
    candidate = replace(older, revision=current.revision + 1)
    if field == "last_acked_sequence":
        candidate = replace(prepare(older, env, "update", TEXT[:3]).state, revision=current.revision + 1)
    elif field == "fence":
        value["cardkit"]["stream"] = lease_metadata(replace(current.lease_state, fence=current.lease_state.fence + 1))
        candidate = current
    with pytest.raises(OfficialError) as caught:
        merge(value, candidate, env)
    assert (
        caught.value.reason_code
        == {
            "last_reserved_sequence": "legacy_sequence_regressed",
            "last_acked_sequence": "legacy_ack_sequence_regressed",
            "fence": "legacy_fence_regressed",
        }[field]
    )


def test_closed_legacy_checkpoint_is_not_implicitly_reopened_but_closed_official_history_can_coexist() -> None:
    env = environment()
    streaming = run_step(run_step(open_stream(env), env, "update", TEXT[:2]), env, "update", TEXT[:3])
    value = legacy_container(env, streaming, "checkpoint")
    value["cardkit"]["checkpoint"] = snapshot(old_checkpoint(streaming, "closed"))
    with pytest.raises(OfficialError) as caught:
        merge(value, streaming, env)
    assert caught.value.reason_code == "legacy_closed_requires_explicit_migration"
    closed = run_step(run_step(streaming, env, "finalize", env.artifact.final_card), env, "close_streaming")
    assert merge(value, closed, env).changed


@pytest.mark.parametrize("field", tuple(environment().scope.__dataclass_fields__))
def test_all_seven_scope_bindings_are_immutable_in_namespace_merge(field: str) -> None:
    env = environment()
    state = new_state(env.scope)
    foreign = replace(binding(env), **{field: "foreign-scope-value"})
    with pytest.raises(OfficialError) as caught:
        merge_official_reconciliation(
            {},
            binding=foreign,
            current_row_revision=0,
            expected_row_revision=0,
            expected_namespace_fingerprint=namespace_fingerprint({}),
            state=state,
        )
    assert caught.value.reason_code == "namespace_binding_mismatch"


@pytest.mark.parametrize("row", [True, -1, 1.5, "7"])
def test_row_revision_requires_an_exact_nonnegative_integer(row: object) -> None:
    env = environment()
    with pytest.raises(OfficialError):
        merge({}, new_state(env.scope), env, row=row)


def test_both_row_cas_and_namespace_cas_are_required_without_mutating_input() -> None:
    env = environment()
    state = open_stream(env)
    value = legacy_container(env, state)
    original = copy.deepcopy(value)
    for change in ({"expected_row": 6}, {"expected_fp": "a" * 64}):
        with pytest.raises(OfficialError) as caught:
            merge(value, state, env, **change)
        assert caught.value.reason_code == "namespace_cas_conflict" and value == original


@pytest.mark.parametrize("change", ["schema", "scope", "revision", "stream", "checkpoint"])
def test_malformed_legacy_namespace_needs_explicit_migration_without_destroying_proof(change: str) -> None:
    env = environment()
    state = open_stream(env)
    value = legacy_container(env, state)
    if change == "schema":
        value["cardkit"]["schema"] = "legacy-unrecognized"
    elif change == "scope":
        value["cardkit"]["binding"]["owner_id"] = "foreign-owner"
    elif change == "revision":
        value["cardkit"]["revision"] = True
    else:
        value["cardkit"][change] = []
    original = copy.deepcopy(value)
    with pytest.raises(ValueError):
        merge(value, state, env)
    assert value == original


@pytest.mark.parametrize(
    "field", ["revision", "last_reserved_sequence", "last_acked_sequence", "fence", "card_id", "message_id"]
)
def test_current_official_namespace_rejects_rollback_or_remote_identity_change(field: str) -> None:
    env = environment()
    old = open_stream(env)
    prepared = prepare(old, env, "update", TEXT[:3]).state
    current = acknowledge(dispatch(prepare(old, env, "update", TEXT[:3]), env), env)
    saved = merge({}, current, env).as_dict()
    if field == "revision":
        candidate = replace(current, revision=current.revision - 1)
    elif field == "last_reserved_sequence":
        candidate = replace(old, revision=current.revision + 1)
    elif field == "last_acked_sequence":
        candidate = replace(prepared, revision=current.revision + 1)
    elif field == "fence":
        candidate = replace(
            current,
            revision=current.revision + 1,
            lease_state=replace(current.lease_state, fence=current.lease_state.fence - 1),
        )
    else:
        value = "67890" if field == "card_id" else "om_reboundSynthetic"
        candidate = replace(
            current,
            revision=current.revision + 1,
            **{field: value},
            lease_state=replace(current.lease_state, **{field: value}),
        )
    with pytest.raises(OfficialError):
        merge(saved, candidate, env, row=8)


def test_dispatched_restore_stays_unknown_and_cannot_be_overwritten_by_prepared_or_a_new_operation() -> None:
    env = environment()
    old = open_stream(env)
    initial = prepare(old, env, "update", TEXT[:3])
    sent = dispatch(initial, env)
    saved = merge({}, sent, env).as_dict()
    restored = restore_state(state_metadata(sent), scope=env.scope)
    assert restored.phase == "uncertain"
    candidate = replace(
        initial.state,
        revision=restored.revision + 1,
        lease_state=replace(initial.state.lease_state, fence=sent.lease_state.fence),
    )
    with pytest.raises(OfficialError) as caught:
        merge(saved, candidate, env, row=8)
    assert caught.value.reason_code == "official_unknown_cannot_retry"
    final_request = prepare(old, env, "finalize", env.artifact.final_card)
    other = replace(dispatch(final_request, env), revision=restored.revision + 1)
    with pytest.raises(OfficialError) as caught:
        merge(saved, other, env, row=8)
    assert caught.value.reason_code == "official_unknown_operation_changed"


def test_unknown_operation_can_only_settle_with_matching_operation_and_bound_remote_evidence() -> None:
    env = environment()
    sent = dispatch(prepare(open_stream(env), env, "update", TEXT[:3]), env)
    saved = merge({}, sent, env).as_dict()
    unknown = settle_outcome(
        sent,
        OfficialOutcome("uncertain", "synthetic-timeout"),
        evidence_ref="synthetic-unknown-observation",
        token=TOKEN,
        fence=sent.lease_state.fence,
        clock=env.clock,
        expected_revision=sent.revision,
    )
    settled = acknowledge(sent, env)
    assert merge(saved, unknown, env, row=8).changed
    assert merge(saved, settled, env, row=8).changed
    assert asdict(settled.scope) == asdict(binding(env))

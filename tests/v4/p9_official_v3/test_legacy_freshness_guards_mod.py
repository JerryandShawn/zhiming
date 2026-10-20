"""Independent legacy boundary rejection; no transport and no blind evaluation input."""

import copy
import socket
from dataclasses import replace
from datetime import timedelta
from random import Random

import pytest
from legacy_freshness_support_mod import (
    AT,
    BODY,
    CARD,
    DIGEST,
    SCOPE,
    TOKEN,
    acquire,
    checkpoint,
    dispatch,
    envelope,
    merge,
    prepared,
    proof,
    settled,
)

from mingjing_core.adapters.channels.card_limits_official_v3 import MAX_SEQUENCE, validate_sequence
from mingjing_core.adapters.channels.cardkit_contracts import CardKitStateError, PendingOperation
from mingjing_core.adapters.channels.stream_outbox_v2 import (
    StreamError,
    fallback_intent,
    next_intent,
    prepare_intent,
    restore_state,
    state_metadata,
)
from mingjing_core.timekit.clock import FrozenClock


@pytest.fixture(autouse=True)
def isolated_legacy_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("独立投递守卫测试不得连接外部服务")

    for name in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)


@pytest.mark.parametrize("field", tuple(SCOPE.__dataclass_fields__))
def test_persisted_metadata_cannot_restore_under_another_one_of_seven_bindings(field: str) -> None:
    value = state_metadata(prepared("update"))
    frozen = copy.deepcopy(value)
    with pytest.raises(StreamError):
        restore_state(value, scope=replace(SCOPE, **{field: "different-binding"}))
    assert value == frozen


@pytest.mark.parametrize(
    "change",
    [
        {"raw_token": TOKEN},
        {"schema": "unknown-version"},
        {"intent": []},
        {"intent": {"operation_id": "bad-extra", "kind": "create"}},
        {"history": {}},
        {"history": [{"intent": {}, "status": "acked", "extra": "not-allowed"}]},
        {"revision": True},
        {"phase": "silently-ready"},
        {"last_reserved_sequence": -1},
        {"dispatch_fingerprint": "not-a-sha256"},
    ],
)
def test_metadata_corruption_is_not_a_new_dispatch_permission(change: dict) -> None:
    value = state_metadata(prepared())
    value.update(copy.deepcopy(change))
    with pytest.raises(StreamError) as caught:
        restore_state(value, scope=SCOPE)
    assert BODY not in str(caught.value) and TOKEN not in str(caught.value)


@pytest.mark.parametrize("expiry", ["not-an-instant", "2026-10-21T01:02:03", 17, None])
def test_lease_expiry_metadata_must_remain_aware_and_parseable(expiry: object) -> None:
    value = state_metadata(acquire(prepared(), FrozenClock(AT)))
    value["lease"]["expires_at"] = expiry
    with pytest.raises(StreamError):
        restore_state(value, scope=SCOPE)


def test_missing_metadata_member_and_wrong_typed_state_are_safely_rejected() -> None:
    value = state_metadata(prepared())
    value.pop("scope_fingerprint")
    with pytest.raises(StreamError):
        restore_state(value, scope=SCOPE)
    with pytest.raises(StreamError):
        state_metadata(value)


@pytest.mark.parametrize("kind", ["create", "send"])
@pytest.mark.parametrize("sequence", [True, 0, 1, 1.5, "1"])
def test_create_and_send_cannot_acquire_a_reserved_update_sequence(kind: str, sequence: object) -> None:
    old = None if kind == "create" else checkpoint("created")
    with pytest.raises(StreamError):
        prepare_intent(
            SCOPE, operation_id="unsequenced", kind=kind, payload_fingerprint=DIGEST, checkpoint=old, sequence=sequence
        )


@pytest.mark.parametrize("sequence", [True, 0, 3, 5, 4.0, "4"])
def test_resume_reserves_exactly_the_next_integer_without_reusing_an_acked_sequence(sequence: object) -> None:
    with pytest.raises(StreamError):
        prepare_intent(
            SCOPE,
            operation_id="bad-sequence",
            kind="update",
            payload_fingerprint=DIGEST,
            checkpoint=checkpoint(),
            sequence=sequence,
        )


@pytest.mark.parametrize("reserved", [MAX_SEQUENCE - 1, MAX_SEQUENCE, MAX_SEQUENCE + 19])
def test_legacy_sequence_candidate_crosses_official_wire_guard_only_within_int32(reserved: int) -> None:
    old = checkpoint(reserved=reserved)
    state = prepared("update", reserved=reserved)
    assert state.card_id == old.card_id and state.message_id == old.message_id
    assert state.intent.sequence == reserved + 1
    if reserved < MAX_SEQUENCE:
        assert validate_sequence(state.intent.sequence) == MAX_SEQUENCE
    else:
        with pytest.raises(ValueError, match="exhausted"):
            validate_sequence(state.intent.sequence)


@pytest.mark.parametrize("phase", ["uncertain", "in_flight", "closed", "fallback_pending"])
def test_checkpoint_with_unsettled_or_final_remote_operation_cannot_be_reprepared(phase: str) -> None:
    pending = PendingOperation("update", "old-pending", DIGEST, 3, 0)
    old = replace(
        checkpoint(),
        phase=phase,
        pending=pending if phase in {"uncertain", "in_flight"} else None,
        final_fingerprint=DIGEST,
    )
    with pytest.raises(StreamError):
        prepare_intent(SCOPE, operation_id="duplicate", kind="update", payload_fingerprint=DIGEST, checkpoint=old)


@pytest.mark.parametrize("field", tuple(CARD.__dataclass_fields__))
def test_checkpoint_resume_cannot_import_another_owner_subject_target_or_business(field: str) -> None:
    old = replace(checkpoint(), scope=replace(CARD, **{field: "foreign-checkpoint"}))
    with pytest.raises(StreamError):
        prepare_intent(SCOPE, operation_id="foreign-resume", kind="update", payload_fingerprint=DIGEST, checkpoint=old)


@pytest.mark.parametrize("old", [[], {"phase": "streaming"}, replace(checkpoint(), initial_fingerprint=None)])
def test_raw_or_incomplete_checkpoint_does_not_bypass_validation(old: object) -> None:
    with pytest.raises(StreamError):
        prepare_intent(SCOPE, operation_id="bad-checkpoint", kind="update", payload_fingerprint=DIGEST, checkpoint=old)


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
@pytest.mark.parametrize("field", tuple(SCOPE.__dataclass_fields__))
def test_validated_run_and_lease_do_not_relax_any_of_seven_scope_bindings(boundary: str, field: str) -> None:
    clock = FrozenClock(AT)
    state = prepared("update")
    state = acquire(state, clock) if boundary == "dispatch" else state
    evidence = replace(proof(state, boundary, clock), scope=replace(SCOPE, **{field: "foreign"}))
    with pytest.raises(StreamError):
        (acquire if boundary == "claim" else dispatch)(state, clock, evidence)


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
@pytest.mark.parametrize("category", ["source", "dependency"])
def test_self_consistent_but_partial_manifest_is_insufficient(boundary: str, category: str) -> None:
    clock = FrozenClock(AT)
    state = prepared("update")
    state = acquire(state, clock) if boundary == "dispatch" else state
    valid = proof(state, boundary, clock)
    selected = tuple(item for item in valid.versions if item.category == category)
    incomplete = replace(
        valid, versions=selected, expected_manifest=tuple((v.category, v.identity, v.expected_hash) for v in selected)
    )
    with pytest.raises(StreamError):
        (acquire if boundary == "claim" else dispatch)(state, clock, incomplete)


@pytest.mark.parametrize("change", ["not-a-list", "bad-shape", "bad-category", "duplicate", "missing", "extra"])
def test_manifest_declaration_cannot_hide_or_add_current_source_rows(change: str) -> None:
    valid = proof(prepared(), "claim", FrozenClock(AT))
    options = {
        "not-a-list": {"source": "guard-user-source"},
        "bad-shape": (("source", "guard-user-source"),),
        "bad-category": (("anything", "guard-user-source", "a" * 64),),
        "duplicate": (*valid.expected_manifest, valid.expected_manifest[0]),
        "missing": valid.expected_manifest[:1],
        "extra": (*valid.expected_manifest, ("source", "absent-row", "c" * 64)),
    }
    with pytest.raises(StreamError):
        replace(valid, expected_manifest=options[change])


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
@pytest.mark.parametrize("change", ["false-validation", "other-answer", "invalid-receipt", "empty-text"])
def test_schema_validity_and_whole_body_stay_mandatory_at_both_boundaries(boundary: str, change: str) -> None:
    clock = FrozenClock(AT)
    state = acquire(prepared(), clock) if boundary == "dispatch" else prepared()
    body = envelope()
    if change == "false-validation":
        body["validation"]["valid"] = False
    elif change == "other-answer":
        body["answer"] = "an unvalidated alternative"
    elif change == "invalid-receipt":
        body["receipts"] = [{"write_status": "saved", "revision": False}]
    else:
        body["text"] = ""
    with pytest.raises(StreamError) as caught:
        (acquire if boundary == "claim" else dispatch)(state, clock, proof(state, boundary, clock, body=body))
    assert BODY not in str(caught.value)


@pytest.mark.parametrize("kind", ["update", "close"])
def test_settled_operation_replay_is_noop_and_cannot_change_rejected_payload(kind: str) -> None:
    state = settled(FrozenClock(AT), kind, refused=True)
    replay = next_intent(
        state,
        operation_id=state.intent.operation_id,
        kind=kind,
        payload_fingerprint=DIGEST,
        expected_revision=state.revision,
    )
    assert replay is state
    with pytest.raises(StreamError):
        next_intent(
            state,
            operation_id=state.intent.operation_id,
            kind=kind,
            payload_fingerprint="f" * 64,
            expected_revision=state.revision,
        )
    with pytest.raises(StreamError):
        next_intent(
            state,
            operation_id="new-key-same-effect",
            kind=kind,
            payload_fingerprint="f" * 64,
            expected_revision=state.revision,
        )


@pytest.mark.parametrize("field", ["revision", "fence", "last_reserved_sequence", "last_acked_sequence"])
def test_namespace_rejects_regression_even_when_host_supplies_current_row_cas(field: str) -> None:
    state = replace(prepared("update"), revision=10, fence=4)
    initial = merge({"old_proof": {"delivered": False}}, state)
    original = initial.as_dict()
    changes = {"revision": 11, field: getattr(state, field) - 1}
    if field == "last_reserved_sequence":
        changes.update(intent=replace(state.intent, sequence=state.intent.sequence - 1), last_acked_sequence=2)
    candidate = replace(state, **changes)
    with pytest.raises(CardKitStateError):
        merge(original, candidate, row=initial.next_row_revision)
    assert initial.as_dict() == original


@pytest.mark.parametrize(
    "corruption", ["stream-not-object", "stream-metadata", "checkpoint-not-object", "checkpoint-data"]
)
def test_existing_namespace_corruption_never_overwrites_prior_proof(corruption: str) -> None:
    initial = merge({"evidence_ref": "legacy-proof"}, prepared())
    current = initial.as_dict()
    if corruption.startswith("stream"):
        current["cardkit"]["stream"] = [] if corruption == "stream-not-object" else {"revision": 0, "fence": 0}
    else:
        current["cardkit"]["checkpoint"] = [] if corruption == "checkpoint-not-object" else {"checkpoint": []}
    frozen = copy.deepcopy(current)
    with pytest.raises(CardKitStateError):
        merge(current, prepared(), row=initial.next_row_revision)
    assert current == frozen


@pytest.mark.parametrize("age", [timedelta(0), timedelta(hours=1), timedelta(days=367)])
def test_unknown_metadata_cannot_be_released_by_new_operation_or_freshness_or_time(age: timedelta) -> None:
    clock = FrozenClock(AT)
    sent = dispatch(acquire(prepared("update"), clock), clock)
    unknown = restore_state(state_metadata(sent), scope=SCOPE)
    installed = merge({"evidence_ref": "immutable-proof", "other": {"flags": [1]}}, unknown)
    clock.advance(age)
    with pytest.raises(StreamError):
        acquire(unknown, clock)
    with pytest.raises(StreamError):
        next_intent(
            unknown,
            operation_id="unknown-cannot-bypass",
            kind="update",
            payload_fingerprint=DIGEST,
            expected_revision=unknown.revision,
        )
    with pytest.raises(CardKitStateError):
        merge(
            installed.as_dict(),
            replace(prepared("update"), revision=unknown.revision + 1, fence=unknown.fence),
            row=installed.next_row_revision,
        )
    assert fallback_intent(unknown) is None
    assert installed.as_dict()["other"] == {"flags": [1]}


def test_one_thousand_random_changed_source_or_dependency_rows_block_sending() -> None:
    rng = Random(2026102106)
    for _ in range(1000):
        clock = FrozenClock(AT + timedelta(seconds=rng.randrange(1_000_000)))
        boundary = rng.choice(("claim", "dispatch"))
        state = acquire(prepared("update"), clock) if boundary == "dispatch" else prepared("update")
        valid = proof(state, boundary, clock)
        versions = list(valid.versions)
        index = rng.randrange(2)
        field, value = rng.choice((("active", False), ("revoked", True), ("current_hash", "e" * 64)))
        versions[index] = replace(versions[index], **{field: value})
        with pytest.raises(StreamError):
            (acquire if boundary == "claim" else dispatch)(state, clock, replace(valid, versions=tuple(versions)))

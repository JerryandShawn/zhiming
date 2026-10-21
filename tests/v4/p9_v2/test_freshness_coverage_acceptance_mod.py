"""Current source proofs are required after recovery and again immediately before dispatch."""

from dataclasses import replace
from datetime import timedelta

import pytest

from mingjing_core.adapters.channels.stream_outbox_v2 import (
    StreamError,
    VersionEvidence,
    recover_expired,
    renew,
    restore_state,
    state_metadata,
)
from mingjing_core.timekit.clock import FrozenClock
from tests.v4.p9_v2.coverage_support_acceptance_mod import AT, TOKEN, TTL, acquire, dispatch, evidence, prepared


@pytest.mark.parametrize("kind", ["create", "send", "update", "close"])
@pytest.mark.parametrize("change", ["source", "dependency", "epoch", "time", "revision"])
def test_successful_claim_does_not_approve_a_later_changed_dispatch(kind: str, change: str) -> None:
    clock = FrozenClock(AT)
    leased = restore_state(state_metadata(acquire(prepared(kind), clock)), scope=prepared(kind).scope)
    valid = evidence(leased, "dispatch", clock)
    if change in {"source", "dependency"}:
        versions = tuple(replace(item, revoked=True) if item.category == change else item for item in valid.versions)
        stale = replace(valid, versions=versions)
    elif change == "epoch":
        stale = replace(valid, current_source_epoch=valid.current_source_epoch + 1)
    elif change == "time":
        stale = replace(valid, checked_at=valid.checked_at - timedelta(microseconds=1))
    else:
        stale = replace(valid, expected_revision=valid.expected_revision - 1)
    with pytest.raises(StreamError):
        dispatch(leased, clock, proof=stale)
    assert leased.attempts == 0 and leased.phase == "leased"


def test_renewal_is_not_source_reauthorization() -> None:
    clock = FrozenClock(AT)
    leased = acquire(prepared("update"), clock)
    clock.advance(timedelta(seconds=1))
    extended = renew(leased, token=TOKEN, fence=leased.fence, expected_revision=leased.revision, clock=clock, ttl=TTL)
    proof = evidence(extended, "dispatch", clock)
    proof = replace(proof, versions=tuple(replace(item, active=False) for item in proof.versions))
    with pytest.raises(StreamError) as caught:
        dispatch(extended, clock, proof=proof)
    assert caught.value.reason_code == "dependencies_or_sources_changed"


def test_reclaimed_unsent_lease_cannot_reuse_pre_expiry_proof_even_when_payload_matches() -> None:
    clock = FrozenClock(AT)
    leased = acquire(prepared("update"), clock)
    old = evidence(leased, "dispatch", clock)
    clock.advance(TTL)
    recovered = recover_expired(leased, expected_revision=leased.revision, clock=clock)
    new = acquire(recovered, clock, token="replacement-secret")
    with pytest.raises(StreamError):
        dispatch(new, clock, token="replacement-secret", proof=old)
    assert dispatch(new, clock, token="replacement-secret").attempts == 1


@pytest.mark.parametrize("field,value", [("active", 1), ("revoked", 0), ("category", 1), ("category", "profile")])
def test_version_projection_types_do_not_coerce_authorization_flags(field: str, value: object) -> None:
    data = dict(category="source", identity="fictional-source", expected_hash="a" * 64, current_hash="a" * 64)
    with pytest.raises(StreamError):
        VersionEvidence(**(data | {field: value}))


@pytest.mark.parametrize(
    "fields",
    [
        {"scope": None},
        {"purpose": "send"},
        {"expected_revision": True},
        {"expected_source_epoch": True},
        {"current_source_epoch": False},
        {"versions": None},
        {"versions": [{"category": "source"}]},
        {"validated_payload": ["not-an-object"]},
    ],
)
def test_untyped_current_rows_cannot_become_a_trusted_proof(fields: dict) -> None:
    proof = evidence(prepared(), "claim", FrozenClock(AT))
    with pytest.raises(StreamError):
        replace(proof, **fields)


def test_source_and_dependency_namespaces_can_share_an_id_without_losing_either_current_row() -> None:
    clock, state = FrozenClock(AT), prepared()
    proof = evidence(state, "claim", clock)
    versions = tuple(replace(item, identity="same-visible-id") for item in proof.versions)
    complete = replace(
        proof,
        versions=versions,
        expected_manifest=tuple((item.category, item.identity, item.expected_hash) for item in versions),
    )
    assert acquire(state, clock, proof=complete).phase == "leased"


@pytest.mark.parametrize("state_container", [None, {}, "snapshot"])
def test_restore_requires_a_versioned_metadata_container(state_container: object) -> None:
    with pytest.raises(StreamError):
        restore_state(state_container, scope=prepared().scope)

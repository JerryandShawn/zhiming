"""Namespace CAS preserves existing delivery proofs and never supplies send authorization."""

import random
from dataclasses import replace

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import CardCheckpoint, CardKitStateError, CardScope
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import (
    ReconciliationBinding,
    merge_cardkit_reconciliation,
    namespace_fingerprint,
)

SCOPE = CardScope("owner", "self", "open", "business")
BINDING = ReconciliationBinding.for_card(SCOPE, outbox_id="outbox", run_id="run")


def merge(current, checkpoint=None, *, row=0, expected_row=None, expected_hash=None, binding=BINDING):
    return merge_cardkit_reconciliation(
        current,
        binding=binding,
        current_row_revision=row,
        expected_row_revision=row if expected_row is None else expected_row,
        expected_namespace_fingerprint=namespace_fingerprint(current) if expected_hash is None else expected_hash,
        checkpoint=checkpoint or CardCheckpoint(SCOPE),
    )


def test_old_delivery_proof_and_nested_unknown_siblings_survive_without_aliasing():
    original = {"delivered": False, "evidence_ref": "proof", "future": {"nested": [1, 2]}}
    result = merge(original)
    current = result.as_dict()
    current["cardkit"]["future_writer"] = {"lease_info": ["opaque"]}
    following = merge(current, replace(CardCheckpoint(SCOPE), version=1), row=1).as_dict()
    assert following["evidence_ref"] == "proof" and following["delivered"] is False
    assert following["cardkit"]["future_writer"] == {"lease_info": ["opaque"]}
    following["future"]["nested"].append(3)
    assert original["future"]["nested"] == [1, 2]
    assert result.as_dict()["future"]["nested"] == [1, 2]


def test_replaying_identical_patch_is_noop_without_incrementing_either_revision():
    first = merge({})
    assert first.changed and first.next_row_revision == 1
    second = merge(first.as_dict(), row=1)
    assert not second.changed and second.next_row_revision == 1
    assert second.namespace_fingerprint == first.namespace_fingerprint


@pytest.mark.parametrize("key", ["owner_id", "subject_id", "outbox_id", "run_id", "business_id", "channel", "target"])
def test_existing_business_binding_cannot_change(key):
    current = merge({}).as_dict()
    with pytest.raises(CardKitStateError, match="binding_changed"):
        merge(current, row=1, binding=replace(BINDING, **{key: "other"}))


@pytest.mark.parametrize("revision", [True, -1, "1", 1.1, None])
def test_invalid_row_revisions_cannot_become_cas_authorization(revision):
    with pytest.raises(CardKitStateError, match="revision"):
        merge({}, row=revision)


def test_stale_row_and_namespace_cas_are_both_checked():
    first = merge({})
    with pytest.raises(CardKitStateError, match="cas_conflict"):
        merge(first.as_dict(), row=1, expected_row=0)
    with pytest.raises(CardKitStateError, match="cas_conflict"):
        merge(first.as_dict(), row=1, expected_hash=namespace_fingerprint({}))


@pytest.mark.parametrize("legacy", [None, "legacy", [], {"schema": "unknown"}])
def test_legacy_namespace_is_never_silently_overwritten(legacy):
    with pytest.raises(CardKitStateError, match="requires_adapter"):
        merge({"cardkit": legacy})


def test_checkpoint_identity_and_version_cannot_regress_or_reuse_revision():
    current = merge({}, replace(CardCheckpoint(SCOPE), version=2)).as_dict()
    with pytest.raises(CardKitStateError, match="regressed"):
        merge(current, replace(CardCheckpoint(SCOPE), version=1), row=1)
    with pytest.raises(CardKitStateError, match="scope_mismatch"):
        merge(current, CardCheckpoint(replace(SCOPE, open_id="other")), row=1)
    with pytest.raises(CardKitStateError):
        merge(current, replace(CardCheckpoint(SCOPE), version=2, last_attempt_ms=1), row=1)


def test_reconciliation_metadata_never_accepts_nonfinite_or_non_json_values():
    for value in (float("nan"), float("inf"), object()):
        with pytest.raises(CardKitStateError):
            merge({"future": value})


def test_remote_card_identity_cannot_change_even_with_a_new_revision():
    checkpoint = CardCheckpoint(SCOPE, phase="created", version=2, card_id="card-A", initial_fingerprint="a" * 64)
    current = merge({}, checkpoint).as_dict()
    with pytest.raises(CardKitStateError, match="remote_identity_changed"):
        merge(current, replace(checkpoint, card_id="card-B", version=3), row=1)


def test_a_thousand_random_cas_updates_preserve_unknown_fields_and_proof():
    rng = random.Random(20261021)
    current = {"delivered": False, "evidence_ref": "immutable-proof", "other": {"writer": [1]}}
    row = 0
    for version in range(1000):
        before = namespace_fingerprint(current)
        result = merge(current, replace(CardCheckpoint(SCOPE), version=version), row=row)
        assert result.expected_namespace_fingerprint == before
        current, row = result.as_dict(), result.next_row_revision
        current["cardkit"]["future_writer"] = {"values": [rng.randrange(10000)]}
        assert current["evidence_ref"] == "immutable-proof" and current["other"] == {"writer": [1]}
        with pytest.raises(CardKitStateError, match="cas_conflict"):
            merge(current, replace(CardCheckpoint(SCOPE), version=version + 1), row=row, expected_hash=before)

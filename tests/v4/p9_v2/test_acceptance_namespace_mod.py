"""Independent deep-copy, complete row/namespace CAS and legacy proof preservation tests."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import CardCheckpoint, CardKitStateError, CardScope
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import (
    ReconciliationBinding,
    merge_cardkit_reconciliation,
    namespace_fingerprint,
)

TRUTH = json.loads((Path(__file__).parent / "fixtures/acceptance_expected_mod.json").read_bytes())
CARD = CardScope("owner", "self", "ou_synthetic", "business")
BINDING = ReconciliationBinding.for_card(CARD, outbox_id="outbox", run_id="run")


def legacy_proof():
    value = copy.deepcopy(TRUTH["reconciliation_seed"])
    value.pop("cardkit")
    return value


def merge(value, checkpoint=None, *, revision=7, expected=None, fingerprint=None, binding=BINDING):
    return merge_cardkit_reconciliation(
        value,
        binding=binding,
        current_row_revision=revision,
        expected_row_revision=revision if expected is None else expected,
        expected_namespace_fingerprint=namespace_fingerprint(value) if fingerprint is None else fingerprint,
        checkpoint=checkpoint or CardCheckpoint(CARD),
    )


def installed():
    result = merge(legacy_proof())
    value = result.as_dict()
    value["cardkit"]["unknown_inside"] = copy.deepcopy(TRUTH["reconciliation_seed"]["cardkit"]["unknown_inside"])
    return value


def test_unversioned_cardkit_state_is_rejected_without_destroying_legacy_evidence():
    source = copy.deepcopy(TRUTH["reconciliation_seed"])
    expected = copy.deepcopy(source)
    with pytest.raises(CardKitStateError):
        merge(source)
    assert source == expected


def test_current_namespace_preserves_old_delivery_proof_and_nested_unknown_siblings():
    source = installed()
    expected = copy.deepcopy(source)
    checkpoint = CardCheckpoint(CARD, phase="created", version=1, card_id="card-one", initial_fingerprint="a" * 64)
    result = merge(source, checkpoint)
    updated = result.as_dict()
    assert result.changed and result.next_row_revision == 8
    assert {key: value for key, value in updated.items() if key != "cardkit"} == legacy_proof()
    assert updated["cardkit"]["unknown_inside"] == expected["cardkit"]["unknown_inside"]
    assert source == expected
    source["unknown_sibling"]["items"][1]["nested"] = False
    source["cardkit"]["unknown_inside"]["preserve"].append(99)
    assert result.as_dict() == updated
    updated["cardkit"]["unknown_inside"]["preserve"].clear()
    assert result.as_dict()["cardkit"]["unknown_inside"]["preserve"] == [1, 2, 3]


def test_same_patch_replay_is_a_noop_without_incrementing_row_or_namespace_revision():
    source = legacy_proof()
    first = merge(source)
    second = merge(first.as_dict(), revision=first.next_row_revision)
    assert not second.changed and second.next_row_revision == first.next_row_revision
    assert second.as_dict() == first.as_dict()


def test_compare_and_swap_rejects_concurrent_row_and_unknown_namespace_sibling_changes():
    source = installed()
    old_hash = namespace_fingerprint(source)
    with pytest.raises(CardKitStateError):
        merge(source, revision=8, expected=7, fingerprint=old_hash)
    changed = copy.deepcopy(source)
    changed["cardkit"]["unknown_inside"]["preserve"].append(4)
    with pytest.raises(CardKitStateError):
        merge(changed, fingerprint=old_hash)


@pytest.mark.parametrize("field", list(BINDING.__dataclass_fields__))
def test_installed_binding_cannot_be_rebound_to_another_owner_run_or_target(field):
    source = installed()
    with pytest.raises(CardKitStateError):
        merge(source, binding=replace(BINDING, **{field: "another"}))


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"last_reserved_sequence": 4},
        {"last_acked_sequence": 3},
        {"card_id": "other-card"},
        {"message_id": "other-message"},
    ],
)
def test_checkpoint_identity_and_reserved_sequence_cannot_regress(change):
    checkpoint = CardCheckpoint(
        CARD,
        phase="streaming",
        version=3,
        card_id="card-one",
        message_id="message-one",
        last_reserved_sequence=5,
        last_acked_sequence=4,
        initial_fingerprint="a" * 64,
    )
    first = merge(legacy_proof(), checkpoint)
    with pytest.raises(CardKitStateError):
        merge(first.as_dict(), replace(checkpoint, **change), revision=first.next_row_revision)


@pytest.mark.parametrize("revision", [True, -1, 1.5])
def test_cas_revision_is_a_strict_nonnegative_integer(revision):
    with pytest.raises(CardKitStateError):
        merge(legacy_proof(), revision=revision)

"""Independent stream/legacy checkpoint merge composition without database authority."""

import copy
from dataclasses import replace

import pytest
from test_acceptance_lifecycle_mod import streaming
from test_acceptance_namespace_mod import BINDING, CARD, TRUTH, legacy_proof
from test_acceptance_stream_mod import AT, SCOPE, dispatched, leased, prepared

from mingjing_core.adapters.channels.cardkit_contracts import CardCheckpoint, CardKitStateError
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import (
    merge_cardkit_reconciliation,
    namespace_fingerprint,
)
from mingjing_core.adapters.channels.stream_outbox_v2 import restore_state, state_metadata
from mingjing_core.timekit.clock import FrozenClock


def merge_stream(value, stream, *, revision=1, checkpoint=None):
    return merge_cardkit_reconciliation(
        value,
        binding=BINDING,
        current_row_revision=revision,
        expected_row_revision=revision,
        expected_namespace_fingerprint=namespace_fingerprint(value),
        stream=stream,
        checkpoint=checkpoint,
    )


def test_acked_stream_metadata_does_not_replace_old_delivery_proof_or_unknown_siblings():
    state = streaming(FrozenClock(AT))
    first = merge_stream(legacy_proof(), state)
    current = first.as_dict()
    current["cardkit"]["unknown_inside"] = copy.deepcopy(TRUTH["reconciliation_seed"]["cardkit"]["unknown_inside"])
    checkpoint = CardCheckpoint(
        CARD,
        phase="streaming",
        version=1,
        card_id=state.card_id,
        message_id=state.message_id,
        initial_fingerprint="a" * 64,
    )
    frozen = copy.deepcopy(current)
    merged = merge_stream(current, state, revision=first.next_row_revision, checkpoint=checkpoint)
    result = merged.as_dict()
    assert current == frozen
    assert {key: value for key, value in result.items() if key != "cardkit"} == legacy_proof()
    assert result["delivered"] is False
    assert result["cardkit"]["stream"] == state_metadata(state)
    assert result["cardkit"]["unknown_inside"] == frozen["cardkit"]["unknown_inside"]
    assert merged.changed
    replay = merge_stream(result, state, revision=merged.next_row_revision, checkpoint=checkpoint)
    assert not replay.changed and replay.next_row_revision == merged.next_row_revision


@pytest.mark.parametrize("phase", ["dispatched", "uncertain"])
@pytest.mark.parametrize("forged_phase", ["prepared", "leased"])
def test_namespace_cannot_turn_unknown_dispatch_into_a_new_automatic_attempt(phase, forged_phase):
    clock = FrozenClock(AT)
    state, _ = dispatched(prepared(), clock)
    if phase == "uncertain":
        state = restore_state(state_metadata(state), scope=SCOPE)
    first = merge_stream(legacy_proof(), state)
    source = first.as_dict()
    frozen = copy.deepcopy(source)
    fresh = prepared() if forged_phase == "prepared" else leased(prepared(), clock).state
    candidate = replace(fresh, revision=state.revision + 1, fence=state.fence)
    with pytest.raises(CardKitStateError):
        merge_stream(source, candidate, revision=first.next_row_revision)
    assert source == frozen


@pytest.mark.parametrize("field", list(SCOPE.__dataclass_fields__))
def test_namespace_and_stream_must_bind_the_same_complete_scope(field):
    state = prepared()
    with pytest.raises(CardKitStateError):
        changed = replace(state, scope=replace(SCOPE, **{field: "other"}))
        merge_stream(legacy_proof(), changed)


def test_conflicting_remote_checkpoint_is_rejected_atomically_preserving_stream_and_proof():
    state = streaming(FrozenClock(AT))
    first = merge_stream(legacy_proof(), state)
    source = first.as_dict()
    original = copy.deepcopy(source)
    checkpoint = CardCheckpoint(
        CARD,
        phase="streaming",
        version=1,
        card_id="different-card",
        message_id=state.message_id,
        initial_fingerprint="a" * 64,
    )
    with pytest.raises(CardKitStateError):
        merge_stream(source, state, revision=first.next_row_revision, checkpoint=checkpoint)
    assert source == original

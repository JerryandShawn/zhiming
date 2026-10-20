"""Saving an identical dispatched snapshot is idempotent; it never authorizes another request."""

from dataclasses import asdict

import pytest

from mingjing_core.adapters.channels.cardkit_official_v3 import (
    OfficialOutcome,
    merge_official_reconciliation,
    new_state,
    settle_outcome,
)
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import ReconciliationBinding, namespace_fingerprint

from .support_mod import TOKEN, acknowledge, dispatch, environment, prepare


@pytest.mark.parametrize("phase", ["new", "prepared", "dispatched", "uncertain", "acked"])
def test_identical_official_namespace_write_is_safe_replay(phase: str) -> None:
    env = environment()
    state = new_state(env.scope)
    if phase != "new":
        prepared = prepare(state, env, "create")
        state = prepared.state if phase == "prepared" else dispatch(prepared, env)
        if phase == "acked":
            state = acknowledge(state, env)
        elif phase == "uncertain":
            state = settle_outcome(
                state,
                OfficialOutcome("uncertain", "synthetic_unknown"),
                evidence_ref="offline-proof",
                token=TOKEN,
                fence=state.lease_state.fence,
                clock=env.clock,
                expected_revision=state.revision,
            )
    binding = ReconciliationBinding(**asdict(env.scope))
    first = merge_official_reconciliation(
        {},
        binding=binding,
        current_row_revision=0,
        expected_row_revision=0,
        expected_namespace_fingerprint=namespace_fingerprint({}),
        state=state,
    )
    saved = first.as_dict()
    replay = merge_official_reconciliation(
        saved,
        binding=binding,
        current_row_revision=first.next_row_revision,
        expected_row_revision=first.next_row_revision,
        expected_namespace_fingerprint=namespace_fingerprint(saved),
        state=state,
    )
    assert replay.changed is False
    assert replay.next_row_revision == first.next_row_revision
    assert replay.as_dict() == saved

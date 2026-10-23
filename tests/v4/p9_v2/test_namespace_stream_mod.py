"""Stream metadata remains scoped, monotonic and unable to authorize an unknown send."""

from dataclasses import replace

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import CardKitStateError
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import (
    ReconciliationBinding,
    merge_cardkit_reconciliation,
    namespace_fingerprint,
)
from mingjing_core.adapters.channels.stream_outbox_v2 import StreamIntent, StreamScope, StreamState

BINDING = ReconciliationBinding("owner", "self", "outbox", "run", "business", "feishu", "open")
SCOPE = StreamScope("owner", "self", "outbox", "run", "business", "feishu", "open")


def state():
    return StreamState(SCOPE, StreamIntent("operation", "create", "a" * 64))


def merge(current, stream, row=0):
    return merge_cardkit_reconciliation(
        current,
        binding=BINDING,
        current_row_revision=row,
        expected_row_revision=row,
        expected_namespace_fingerprint=namespace_fingerprint(current),
        stream=stream,
    )


def test_scoped_stream_roundtrip_and_repeated_patch_are_noop():
    result = merge({"evidence_ref": "proof"}, state())
    assert result.as_dict()["evidence_ref"] == "proof"
    assert "token" not in result.as_dict()["cardkit"]["stream"]
    repeated = merge(result.as_dict(), state(), 1)
    assert not repeated.changed and repeated.next_row_revision == 1


def test_stream_from_another_scope_is_rejected():
    with pytest.raises(CardKitStateError, match="scope_mismatch"):
        merge({}, replace(state(), scope=replace(SCOPE, subject_id="another")))


def test_unknown_state_cannot_be_rewritten_as_sendable_or_given_a_new_card():
    unknown = replace(state(), phase="uncertain", revision=3, fence=1, attempts=1, dispatch_fingerprint="b" * 64)
    current = merge({}, unknown).as_dict()
    with pytest.raises(CardKitStateError, match="unknown_cannot_retry"):
        merge(current, replace(state(), revision=4, fence=1), 1)
    with pytest.raises(CardKitStateError, match="regressed"):
        merge(current, replace(unknown, revision=2), 1)


def test_metadata_scope_hash_tampering_is_invalid_even_with_current_cas_hash():
    current = merge({}, state()).as_dict()
    current["cardkit"]["stream"]["scope_fingerprint"] = "c" * 64
    with pytest.raises(CardKitStateError, match="invalid_reconciliation_stream"):
        merge(current, replace(state(), revision=1), 1)

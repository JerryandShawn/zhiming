"""Explicit opt-in offline official-protocol candidates; no HTTP, credentials or default transport."""

from .codec import restore_state, state_metadata
from .contracts import (
    ArtifactEvidence,
    OfficialAck,
    OfficialError,
    OfficialFallback,
    OfficialOperation,
    OfficialOutcome,
    OfficialPolicy,
    OfficialRequest,
    OfficialState,
    PreparedOperation,
)
from .errors import classify_response
from .namespace import merge_official_reconciliation
from .operations import fallback_intent, new_state, prepare_operation, stream_deadline_action
from .transitions import begin_dispatch, claim, reconcile, recover_expired, settle_ack, settle_outcome
from .wire import build_wire_request, initial_card, request_data

__all__ = [
    "ArtifactEvidence",
    "OfficialAck",
    "OfficialError",
    "OfficialFallback",
    "OfficialOperation",
    "OfficialOutcome",
    "OfficialPolicy",
    "OfficialRequest",
    "OfficialState",
    "PreparedOperation",
    "begin_dispatch",
    "build_wire_request",
    "claim",
    "classify_response",
    "fallback_intent",
    "initial_card",
    "merge_official_reconciliation",
    "new_state",
    "prepare_operation",
    "reconcile",
    "recover_expired",
    "request_data",
    "restore_state",
    "settle_ack",
    "settle_outcome",
    "state_metadata",
    "stream_deadline_action",
]

"""Metadata snapshots contain neither card content, raw tokens nor validated payloads."""

from dataclasses import asdict, fields, replace
from datetime import datetime

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint

from .contracts import IntentRecord, StreamError, StreamIntent, StreamLease, StreamScope, StreamState

_FIELDS = frozenset(field.name for field in fields(StreamState)) - {"scope"}


def state_metadata(state: StreamState) -> dict:
    if not isinstance(state, StreamState):
        raise StreamError("stream_state_required")
    _validate_state(state)
    data = {name: getattr(state, name) for name in _FIELDS}
    data["intent"] = asdict(state.intent)
    data["history"] = [{"intent": asdict(item.intent), "status": item.status} for item in state.history]
    data["lease"] = (
        {**asdict(state.lease), "expires_at": state.lease.expires_at.isoformat()} if state.lease is not None else None
    )
    return {"schema": "stream-outbox-v2", "scope_fingerprint": fingerprint(asdict(state.scope)), **data}


def restore_state(value: dict, *, scope: StreamScope) -> StreamState:
    if (
        not isinstance(scope, StreamScope)
        or not isinstance(value, dict)
        or set(value) != _FIELDS | {"schema", "scope_fingerprint"}
    ):
        raise StreamError("state_metadata_shape_invalid")
    if value["schema"] != "stream-outbox-v2" or value["scope_fingerprint"] != fingerprint(asdict(scope)):
        raise StreamError("state_metadata_scope_invalid")
    try:
        data = {name: value[name] for name in _FIELDS}
        data["intent"] = StreamIntent(**data["intent"])
        if data["lease"] is not None:
            raw = data["lease"]
            data["lease"] = StreamLease(**{**raw, "expires_at": datetime.fromisoformat(raw["expires_at"])})
        if not isinstance(data["history"], (tuple, list)):
            raise StreamError("history_metadata_invalid")
        data["history"] = tuple(_history_record(item) for item in data["history"])
        state = StreamState(scope=scope, **data)
        _validate_state(state)
        if state.phase == "dispatched":
            state = replace(state, phase="uncertain", lease=None, revision=state.revision + 1)
        return state
    except StreamError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        raise StreamError("state_metadata_invalid") from None


def _history_record(value: object) -> IntentRecord:
    if not isinstance(value, dict) or set(value) != {"intent", "status"}:
        raise StreamError("history_metadata_invalid")
    return IntentRecord(StreamIntent(**value["intent"]), value["status"])


def _validate_state(state: StreamState) -> None:
    intent = state.intent
    if intent.kind == "fallback":
        raise StreamError("fallback_is_separate_outbox_intent")
    if intent.kind == "create":
        if (state.card_id is not None) != (state.phase == "acked") or state.message_id is not None:
            raise StreamError("created_state_identity_invalid")
    elif intent.kind == "send":
        if state.card_id is None or (state.message_id is not None) != (state.phase == "acked"):
            raise StreamError("sent_state_identity_invalid")
    elif state.card_id is None or state.message_id is None or intent.sequence != state.last_reserved_sequence:
        raise StreamError("streaming_state_identity_invalid")
    if state.phase in {"dispatched", "uncertain"} and state.dispatch_fingerprint is None:
        raise StreamError("dispatch_evidence_missing")
    if state.phase == "acked" and intent.sequence is not None and state.last_acked_sequence != intent.sequence:
        raise StreamError("acked_sequence_invalid")

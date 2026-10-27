"""Metadata-only snapshots; restore never manufactures permission to resend an unknown operation."""

from dataclasses import asdict, fields
from datetime import datetime
from typing import Any

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import StreamScope
from mingjing_core.adapters.channels.stream_outbox_v2 import restore_state as restore_lease
from mingjing_core.adapters.channels.stream_outbox_v2 import state_metadata as lease_metadata

from .contracts import OfficialError, OfficialOperation, OfficialPolicy, OfficialState

SCHEMA = "cardkit-official-v3"
FIELDS = frozenset(row.name for row in fields(OfficialState)) - {"scope"}
TIMES = ("last_attempt_at", "started_at", "not_before")


def state_metadata(state: OfficialState) -> dict[str, Any]:
    if not isinstance(state, OfficialState):
        raise OfficialError("official_state_required")
    from .validation import validate_state

    validate_state(state)
    value = {key: getattr(state, key) for key in FIELDS}
    value["policy"] = asdict(state.policy)
    value["operation"] = asdict(state.operation) if state.operation else None
    value["history"] = [asdict(row) for row in state.history]
    value["lease_state"] = lease_metadata(state.lease_state) if state.lease_state else None
    for key in TIMES:
        value[key] = value[key].isoformat() if value[key] is not None else None
    return {"schema": SCHEMA, "scope_fingerprint": fingerprint(asdict(state.scope)), **value}


def restore_state(value: dict[str, Any], *, scope: StreamScope) -> OfficialState:
    if (
        not isinstance(scope, StreamScope)
        or not isinstance(value, dict)
        or set(value) != FIELDS | {"schema", "scope_fingerprint"}
    ):
        raise OfficialError("snapshot_shape_invalid")
    if value["schema"] != SCHEMA or value["scope_fingerprint"] != fingerprint(asdict(scope)):
        raise OfficialError("snapshot_scope_invalid")
    try:
        raw = {key: value[key] for key in FIELDS}
        raw["policy"] = OfficialPolicy(**raw["policy"])
        raw["operation"] = OfficialOperation(**raw["operation"]) if raw["operation"] is not None else None
        if not isinstance(raw["history"], (list, tuple)):
            raise OfficialError("snapshot_history_invalid")
        raw["history"] = tuple(OfficialOperation(**row) for row in raw["history"])
        raw["lease_state"] = restore_lease(raw["lease_state"], scope=scope) if raw["lease_state"] is not None else None
        if value["lease_state"] is not None and value["lease_state"].get("phase") == "dispatched":
            raw["revision"] += 1
        for key in TIMES:
            raw[key] = datetime.fromisoformat(raw[key]) if raw[key] is not None else None
        return OfficialState(scope, **raw)
    except OfficialError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError):
        raise OfficialError("snapshot_invalid") from None

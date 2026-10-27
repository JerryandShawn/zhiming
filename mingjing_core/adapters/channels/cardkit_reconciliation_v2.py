"""Pure namespace CAS plans; the host must apply them under the Outbox row lock."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from .cardkit_checkpoint import restore_snapshot, snapshot
from .cardkit_contracts import CardCheckpoint, CardKitStateError, CardScope, canonical, fingerprint, identifier

if TYPE_CHECKING:
    from .stream_outbox_v2 import StreamState

SCHEMA = "cardkit.outbox.namespace.v2"
ABSENT = fingerprint({"cardkit_namespace_absent": True})


@dataclass(frozen=True)
class ReconciliationBinding:
    owner_id: str
    subject_id: str
    outbox_id: str
    run_id: str
    business_id: str
    channel: str
    target: str = field(repr=False)  # 待对照飞书官方文档核实；仅接受可信host绑定。

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            identifier(value)

    @classmethod
    def for_card(cls, scope: CardScope, *, outbox_id: str, run_id: str) -> ReconciliationBinding:
        return cls(scope.owner_id, scope.subject_id, outbox_id, run_id, scope.business_id, "feishu", scope.open_id)


@dataclass(frozen=True)
class ReconciliationMerge:
    expected_row_revision: int
    next_row_revision: int
    expected_namespace_fingerprint: str
    namespace_fingerprint: str
    changed: bool
    _json: str = field(repr=False)

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._json)


def _clone(value: Mapping) -> dict:
    if not isinstance(value, Mapping):
        raise CardKitStateError("invalid_reconciliation_object")
    try:
        return json.loads(canonical(dict(value)))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise CardKitStateError("invalid_reconciliation_json") from None


def namespace_fingerprint(reconciliation: Mapping) -> str:
    current = _clone(reconciliation)
    if "cardkit" not in current:
        return ABSENT
    if not isinstance(current["cardkit"], dict):
        raise CardKitStateError("legacy_cardkit_namespace_requires_adapter")
    return fingerprint(current["cardkit"])


def _revision(value: object) -> int:
    if type(value) is not int or value < 0:
        raise CardKitStateError("invalid_reconciliation_revision")
    return value


def _validate_stream(data: dict, binding: ReconciliationBinding) -> None:
    from .stream_outbox_v2 import StreamError, StreamScope, restore_state

    try:
        restore_state(data, scope=StreamScope(**asdict(binding)))
    except StreamError:
        raise CardKitStateError("invalid_reconciliation_stream") from None


def _namespace(current: dict, binding: ReconciliationBinding) -> dict:
    old = current.get("cardkit")
    if "cardkit" not in current:
        return {"schema": SCHEMA, "binding": asdict(binding), "revision": 0}
    if not isinstance(old, dict) or old.get("schema") != SCHEMA:
        raise CardKitStateError("legacy_cardkit_namespace_requires_adapter")
    if old.get("binding") != asdict(binding):
        raise CardKitStateError("reconciliation_binding_changed")
    _revision(old.get("revision"))
    if "stream" in old and not isinstance(old["stream"], dict):
        raise CardKitStateError("invalid_reconciliation_stream")
    if "stream" in old:
        for key in ("revision", "fence"):
            _revision(old["stream"].get(key))
        _validate_stream(old["stream"], binding)
    if "checkpoint" in old and (
        not isinstance(old["checkpoint"], dict) or not isinstance(old["checkpoint"].get("checkpoint"), dict)
    ):
        raise CardKitStateError("invalid_reconciliation_checkpoint")
    if "checkpoint" in old:
        scope = CardScope(binding.owner_id, binding.subject_id, binding.target, binding.business_id)
        restore_snapshot(old["checkpoint"], scope=scope)
    return old


def _checkpoint_data(checkpoint: CardCheckpoint, binding: ReconciliationBinding, old: dict) -> dict:
    if not isinstance(checkpoint, CardCheckpoint) or not isinstance(checkpoint.scope, CardScope):
        raise CardKitStateError("invalid_reconciliation_checkpoint")
    expected = (binding.owner_id, binding.subject_id, binding.target, binding.business_id)
    scope = checkpoint.scope
    if (scope.owner_id, scope.subject_id, scope.open_id, scope.business_id) != expected or binding.channel != "feishu":
        raise CardKitStateError("reconciliation_checkpoint_scope_mismatch")
    data = snapshot(checkpoint)
    restore_snapshot(data, scope=scope)  # Validation only; uncertain recovery belongs to the old client.
    prior = old.get("checkpoint", {}).get("checkpoint", {})
    for name in ("card_id", "message_id"):
        if prior.get(name) is not None and prior[name] != getattr(checkpoint, name):
            raise CardKitStateError("reconciliation_remote_identity_changed")
    for name in ("version", "last_reserved_sequence", "last_acked_sequence"):
        if name in prior and getattr(checkpoint, name) < prior[name]:
            raise CardKitStateError("reconciliation_checkpoint_regressed")
    if prior and data != old["checkpoint"] and checkpoint.version <= prior["version"]:
        raise CardKitStateError("reconciliation_checkpoint_revision_reused")
    return data


def _stream_data(stream: StreamState, binding: ReconciliationBinding, old: dict) -> dict:
    from .stream_outbox_v2 import StreamState, state_metadata

    if not isinstance(stream, StreamState) or asdict(stream.scope) != asdict(binding):
        raise CardKitStateError("reconciliation_stream_scope_mismatch")
    data = _clone(state_metadata(stream))
    _validate_stream(data, binding)  # Validate only; recovery is a separate host transition.
    prior = old.get("stream", {})
    for name in ("revision", "fence", "last_reserved_sequence", "last_acked_sequence"):
        if name in prior and data[name] < prior[name]:
            raise CardKitStateError("reconciliation_stream_regressed")
    for name in ("card_id", "message_id"):
        if prior.get(name) is not None and prior[name] != data[name]:
            raise CardKitStateError("reconciliation_remote_identity_changed")
    if prior and data != prior and data["revision"] <= prior["revision"]:
        raise CardKitStateError("reconciliation_stream_revision_reused")
    if prior.get("phase") in {"dispatched", "uncertain"} and data["phase"] in {"prepared", "leased"}:
        raise CardKitStateError("reconciliation_unknown_cannot_retry")
    return data


def _same_remote(namespace: dict) -> None:
    stream = namespace.get("stream", {})
    checkpoint = namespace.get("checkpoint", {}).get("checkpoint", {})
    for name in ("card_id", "message_id"):
        if stream.get(name) is not None and checkpoint.get(name) is not None and stream[name] != checkpoint[name]:
            raise CardKitStateError("reconciliation_remote_identity_conflict")


def merge_cardkit_reconciliation(
    reconciliation: Mapping,
    *,
    binding: ReconciliationBinding,
    current_row_revision: int,
    expected_row_revision: int,
    expected_namespace_fingerprint: str,
    stream: StreamState | None = None,
    checkpoint: CardCheckpoint | None = None,
) -> ReconciliationMerge:
    """Preserve all proof/sibling fields. This plan alone never authorizes transport or retry."""
    current = _clone(reconciliation)
    if not isinstance(binding, ReconciliationBinding) or (stream is None and checkpoint is None):
        raise CardKitStateError("invalid_reconciliation_patch")
    revision = _revision(current_row_revision)
    if revision != _revision(expected_row_revision) or namespace_fingerprint(current) != expected_namespace_fingerprint:
        raise CardKitStateError("reconciliation_cas_conflict")
    old = _namespace(current, binding)
    updated = _clone(old)
    if stream is not None:
        updated["stream"] = _stream_data(stream, binding, old)
    if checkpoint is not None:
        updated["checkpoint"] = _checkpoint_data(checkpoint, binding, old)
    _same_remote(updated)
    changed = updated != old or "cardkit" not in current
    if changed:
        updated["revision"] = old["revision"] + 1
    current["cardkit"] = updated
    return ReconciliationMerge(
        revision,
        revision + int(changed),
        expected_namespace_fingerprint,
        fingerprint(updated),
        changed,
        canonical(current),
    )

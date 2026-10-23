"""Consistency checks for trusted host evidence; these pure functions cannot verify PostgreSQL."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.adapters.channels.hermes import validated_payload
from mingjing_core.streaming.event_payloads import Core4Envelope
from mingjing_core.streaming.json_values import freeze_json, json_object

from .contracts import StreamError, StreamScope, StreamState, digest, identity, integer, utc


@dataclass(frozen=True)
class VersionEvidence:
    category: str
    identity: str = field(repr=False)
    expected_hash: str
    current_hash: str
    active: bool = True
    revoked: bool = False

    def __post_init__(self) -> None:
        if type(self.category) is not str or self.category not in {"source", "dependency"}:
            raise StreamError("version_category_invalid")
        identity(self.identity)
        digest(self.expected_hash)
        digest(self.current_hash)
        if type(self.active) is not bool or type(self.revoked) is not bool:
            raise StreamError("version_flag_invalid")


@dataclass(frozen=True)
class FreshnessEvidence:
    scope: StreamScope
    operation_id: str
    expected_revision: int
    purpose: str
    checked_at: datetime
    transaction_id: str
    run_status: str
    intent_payload_fingerprint: str
    run_payload_fingerprint: str
    validated_payload: Mapping = field(repr=False)
    versions: tuple[VersionEvidence, ...] = field(repr=False)
    expected_source_epoch: int
    current_source_epoch: int
    expected_manifest: tuple[tuple[str, str, str], ...] = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scope, StreamScope)
            or type(self.purpose) is not str
            or self.purpose not in {"claim", "dispatch"}
        ):
            raise StreamError("freshness_binding_invalid")
        identity(self.operation_id)
        identity(self.transaction_id)
        identity(self.run_status)
        for value in (self.expected_revision, self.expected_source_epoch, self.current_source_epoch):
            integer(value)
        digest(self.intent_payload_fingerprint)
        digest(self.run_payload_fingerprint)
        object.__setattr__(self, "checked_at", utc(self.checked_at))
        try:
            object.__setattr__(self, "validated_payload", freeze_json(json_object(self.validated_payload)))
        except (TypeError, ValueError):
            raise StreamError("validated_payload_invalid") from None
        if not isinstance(self.versions, (tuple, list)) or any(
            not isinstance(item, VersionEvidence) for item in self.versions
        ):
            raise StreamError("version_evidence_invalid")
        object.__setattr__(self, "versions", tuple(self.versions))
        _manifest(self)


def _manifest(evidence: FreshnessEvidence) -> None:
    if not isinstance(evidence.expected_manifest, (tuple, list)):
        raise StreamError("manifest_required")
    entries = []
    for entry in evidence.expected_manifest:
        if not isinstance(entry, (tuple, list)) or len(entry) != 3:
            raise StreamError("manifest_entry_invalid")
        category, item_id, expected_hash = entry
        if type(category) is not str or category not in {"source", "dependency"}:
            raise StreamError("manifest_category_invalid")
        identity(item_id)
        digest(expected_hash)
        entries.append(tuple(entry))
    keys = [(category, item_id) for category, item_id, _ in entries]
    actual = [(item.category, item.identity) for item in evidence.versions]
    if len(set(keys)) != len(keys) or len(set(actual)) != len(actual):
        raise StreamError("manifest_duplicate_entry")
    supplied = {(item.category, item.identity, item.expected_hash) for item in evidence.versions}
    if not entries or supplied != set(entries):
        raise StreamError("manifest_version_set_mismatch")
    object.__setattr__(evidence, "expected_manifest", tuple(entries))


def validate_freshness(state: StreamState, evidence: FreshnessEvidence, purpose: str, now: datetime) -> None:
    if not isinstance(evidence, FreshnessEvidence):
        raise StreamError("trusted_freshness_evidence_required")
    if evidence.scope != state.scope or evidence.operation_id != state.intent.operation_id:
        raise StreamError("freshness_scope_mismatch")
    if evidence.expected_revision != state.revision or evidence.purpose != purpose or evidence.checked_at != utc(now):
        raise StreamError("freshness_transaction_not_current")
    if evidence.run_status not in {"succeeded", "complete", "completed", "validated", "success"}:
        raise StreamError("run_not_successful")
    if evidence.intent_payload_fingerprint != state.intent.payload_fingerprint:
        raise StreamError("intent_payload_changed")
    if evidence.current_source_epoch != evidence.expected_source_epoch:
        raise StreamError("source_epoch_changed")
    categories = {item.category for item in evidence.versions}
    if categories != {"source", "dependency"}:
        raise StreamError("complete_source_and_dependency_evidence_required")
    if any(item.expected_hash != item.current_hash or item.revoked or not item.active for item in evidence.versions):
        raise StreamError("dependencies_or_sources_changed")
    _validate_payload(state, evidence)


def _validate_payload(state: StreamState, evidence: FreshnessEvidence) -> None:
    raw = json_object(evidence.validated_payload)
    if fingerprint(raw) != evidence.run_payload_fingerprint:
        raise StreamError("validated_payload_changed")
    try:
        if raw.get("schema") == "core4.0":
            envelope = Core4Envelope.model_validate(raw)
            if (
                envelope.validation is None
                or envelope.meta is None
                or envelope.meta.core_run.run_id != state.scope.run_id
            ):
                raise StreamError("complete_validated_envelope_required")
            if envelope.meta.subject_id != state.scope.subject_id:
                raise StreamError("validated_subject_mismatch")
            if envelope.answer is not None and envelope.answer != envelope.text:
                raise StreamError("validated_answer_mismatch")
        else:
            validated_payload(raw)
            if raw.get("meta", {}).get("core_run", {}).get("run_id") != state.scope.run_id:
                raise StreamError("validated_run_mismatch")
            if raw.get("meta", {}).get("subject_id") != state.scope.subject_id:
                raise StreamError("validated_subject_mismatch")
    except StreamError:
        raise
    except Exception:
        raise StreamError("complete_validated_envelope_required") from None

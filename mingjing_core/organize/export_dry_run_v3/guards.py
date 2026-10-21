"""Current host facts are required even for previews; exported owner claims are insufficient."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from mingjing_core.memory2.consent_text import has_storage_optout
from mingjing_core.memory2.contracts import MemoryScope, MemorySource, SourceAnchor, utc
from mingjing_core.memory2.sensitivity import classify_sensitivity
from mingjing_core.organize._change_values import LABEL_FIELDS, digest, validate_document
from mingjing_core.streaming.json_values import json_object
from mingjing_core.timekit.clock import Clock

from .contracts import DryRunError, ExportSnapshot, MessagePrecondition


def require_snapshot(snapshot: ExportSnapshot, scope: MemoryScope) -> dict[str, Any]:
    if not isinstance(snapshot, ExportSnapshot) or not isinstance(scope, MemoryScope) or snapshot.scope != scope:
        raise DryRunError("scope_mismatch")
    document = json_object(snapshot.document)
    try:
        validate_document(document, scope.owner_id, scope.subject_id)
    except ValueError:
        raise DryRunError("snapshot_document_invalid") from None
    if any((source.owner_id, source.subject_id) != (scope.owner_id, scope.subject_id) for source in snapshot.sources):
        raise DryRunError("source_scope_mismatch")
    return document


def source_reason(source: MemorySource, *, now: datetime) -> str | None:
    if not source.active or source.revoked:
        return "source_unavailable"
    if source.incognito or source.optout or has_storage_optout(source.text):
        return "source_not_persistent"
    if source.role not in {"user", "assistant"} or (source.role == "user" and source.origin != "current_user"):
        return "source_role_untrusted"
    if source.at > utc(now):
        return "source_future"
    sensitivity = classify_sensitivity(source.text)
    if sensitivity.secret:
        return "secret_forbidden"
    if sensitivity.profile_confirmation:
        return "profile_confirmation_required"
    if sensitivity.categories:
        return "sensitive_confirmation_required"
    return None


def row_reason(row: Mapping[str, Any]) -> str | None:
    if row.get("status") != "active" or row.get("source_status", "active") != "active":
        return "row_unavailable"
    if row.get("incognito") is not False or row.get("retention_scope") != "persistent":
        return "row_not_persistent"
    if row.get("deleted_at") is not None or row.get("revoked_at") is not None:
        return "row_unavailable"
    if type(row.get("current", True)) is not bool or row.get("current", True) is not True:
        return "row_not_current"
    if type(row.get("thread_id")) is not str or not row["thread_id"] or row["thread_id"].startswith("incognito:"):
        return "row_not_persistent"
    return None


def immutable_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in LABEL_FIELDS and key != "revision"}


def precondition(row: dict[str, Any]) -> MessagePrecondition:
    return MessagePrecondition(
        row["id"], row["revision"], row["source_id"], row["source_revision"], digest(immutable_row(row))
    )


def check_anchor(anchor: SourceAnchor, snapshot: ExportSnapshot, clock: Clock) -> str | None:
    source = next((item for item in snapshot.sources if item.id == anchor.source_id), None)
    if source is None or source.revision != anchor.revision:
        return "source_revision_changed"
    reason = source_reason(source, now=clock.now())
    if reason:
        return reason
    if source.text[anchor.start : anchor.end] != anchor.quote or anchor.end > len(source.text):
        return "source_quote_changed"
    return None

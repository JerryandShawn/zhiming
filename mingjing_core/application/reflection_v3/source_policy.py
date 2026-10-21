"""Reject storage-prohibited text before constructing summaries, projections or derived candidates."""

from datetime import datetime

from mingjing_core.memory2.consent_text import has_storage_optout
from mingjing_core.memory2.contracts import MemorySource
from mingjing_core.memory2.sensitivity import classify_sensitivity

from .schedule_contracts import ProcessedSource
from .validation import digest


def source_reason(source: MemorySource, now: datetime, *, allow_sensitive: bool = False) -> str | None:
    if not source.text.strip():
        return "source_empty"
    if not source.active or source.revoked or source.incognito or source.optout:
        return "source_unavailable"
    if source.at > now:
        return "source_time_in_future"
    if has_storage_optout(source.text):
        return "source_storage_optout"
    privacy = classify_sensitivity(source.text)
    if privacy.secret:
        return "secret_never_derived"
    if not allow_sensitive and (privacy.categories or privacy.profile_confirmation):
        return "sensitive_or_birth_confirmation_required"
    if source.role == "user" and source.origin != "current_user":
        return "current_user_source_required"
    if source.role not in {"user", "assistant"}:
        return "conversation_role_required"
    return None


def source_cursor(source: MemorySource) -> ProcessedSource:
    return ProcessedSource(
        source.id, source.revision, digest([source.text, source.at.isoformat(), source.role, source.origin])
    )

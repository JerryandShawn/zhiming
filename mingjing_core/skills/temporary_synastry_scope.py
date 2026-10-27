"""Caller-attested authorization boundary for an opt-in transient reading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, repr=False)
class SynastryBinding:
    owner_user_id: str
    run_id: str
    subject_ids: tuple[str, str]
    revisions: tuple[int, int]
    operation_ids: tuple[str, str]
    compute_operation_id: str
    grant_id: str
    kind: str

    def __post_init__(self) -> None:
        strings = (
            self.owner_user_id,
            self.run_id,
            self.compute_operation_id,
            self.grant_id,
        )
        if any(not isinstance(item, str) or not item.strip() for item in strings):
            raise ValueError("TEMPORARY_SCOPE_INVALID")
        for values in (self.subject_ids, self.revisions, self.operation_ids):
            if type(values) is not tuple or len(values) != 2:
                raise ValueError("TEMPORARY_SCOPE_INVALID")
        if any(type(item) is not int or item < 1 for item in self.revisions):
            raise ValueError("TEMPORARY_SCOPE_INVALID")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.subject_ids + self.operation_ids
        ):
            raise ValueError("TEMPORARY_SCOPE_INVALID")
        if len(set(self.subject_ids)) != 2 or self.kind not in (
            "romantic",
            "friendship",
            "collaboration",
        ):
            raise ValueError("TEMPORARY_SCOPE_INVALID")

    def native_scope(self) -> dict:
        return {
            "owner_user_id": self.owner_user_id,
            "subject_ids": list(self.subject_ids),
            "revisions": list(self.revisions),
            "operation_ids": list(self.operation_ids),
        }


@dataclass(frozen=True, repr=False)
class ConsumedGrant:
    """Trusted callback result, never built from model-supplied consent text."""

    binding: SynastryBinding
    confirmed_at: datetime
    expires_at: datetime
    consumed_operation_id: str
    revoked: bool = False


def utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("TEMPORARY_CLOCK_INVALID")
    return value.astimezone(UTC)

"""Atomic in-memory reference store; production needs the same contract inside a PG transaction."""

import hmac
import threading
from dataclasses import replace
from datetime import datetime
from typing import Protocol

from .action_token_contracts import (
    ActionTokenClaim,
    ActionTokenError,
    ActionTokenRecord,
    TokenConsumption,
    utc,
    validate_digest,
)


class ActionTokenStore(Protocol):
    def put_if_absent(self, record: ActionTokenRecord) -> bool:
        """Insert an immutable hashed capability; false means a digest collision."""
        ...

    def consume(
        self, digest: str, claim: ActionTokenClaim, *, now: datetime
    ) -> TokenConsumption:
        """Verify every binding and expiry and mark used atomically; valid replays must never execute again."""
        ...


def _same_claim(expected: ActionTokenClaim, supplied: ActionTokenClaim) -> bool:
    checks = [
        hmac.compare_digest(
            getattr(expected, key).encode(), getattr(supplied, key).encode()
        )
        for key in expected.__dataclass_fields__
    ]
    return all(checks)


class MemoryActionTokenStore:
    def __init__(self, *, capacity: int = 10000) -> None:
        if type(capacity) is not int or capacity < 1:
            raise ActionTokenError()
        self._capacity = capacity
        self._records: dict[str, ActionTokenRecord] = {}
        self._lock = threading.RLock()

    def put_if_absent(self, record: ActionTokenRecord) -> bool:
        if not isinstance(record, ActionTokenRecord):
            raise ActionTokenError()
        with self._lock:
            if record.digest in self._records:
                return False
            if len(self._records) >= self._capacity:
                raise ActionTokenError()
            self._records[record.digest] = record
            return True

    def consume(
        self, digest: str, claim: ActionTokenClaim, *, now: datetime
    ) -> TokenConsumption:
        validate_digest(digest)
        now = utc(now)
        if not isinstance(claim, ActionTokenClaim):
            raise ActionTokenError()
        with self._lock:
            record = self._records.get(digest)
            if record is None or not _same_claim(record.claim, claim):
                raise ActionTokenError()
            if not record.created_at <= now < record.expires_at:
                raise ActionTokenError()
            replayed = record.used_at is not None
            used_at = record.used_at or now
            if not replayed:
                self._records[digest] = replace(record, used_at=used_at)
            return TokenConsumption(
                claim.owner_id,
                claim.subject_id,
                claim.kind,
                claim.entity_id,
                claim.payload_fingerprint,
                record.operation_id,
                used_at,
                replayed,
            )

    def snapshot(self) -> tuple[ActionTokenRecord, ...]:
        """Return immutable metadata only; neither issued secrets nor action payloads are retained."""
        with self._lock:
            return tuple(self._records.values())

"""Read-only token metadata and refresh intents; no card is sent and no private action is executed."""

from __future__ import annotations

import hmac
import re
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol

from .action_token_contracts import ActionTokenError, ActionTokenRecord, TokenConsumption, validate_digest

EXPIRED_CARD_MESSAGE = "这张卡已过期，我重新发一张"


@dataclass(frozen=True, repr=False)
class TokenMetadata:
    record: ActionTokenRecord
    active: bool = True
    revoked: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.record, ActionTokenRecord)
            or type(self.active) is not bool
            or type(self.revoked) is not bool
        ):
            raise ActionTokenError()


class TokenMetadataLookup(Protocol):
    def lookup(self, digest: str) -> TokenMetadata | None:
        """Return current authorized metadata, never raw tokens or action payloads.

        The PG host must share the owner transaction with token consume and the
        effect. A bare read port alone does not prove durable revocation fencing.
        """
        ...


class SnapshotTokenStore(Protocol):
    def snapshot(self) -> tuple[ActionTokenRecord, ...]: ...


class MemoryTokenMetadataLookup:
    """Only the old store's public immutable snapshot is used; this is not a PG authority."""

    durable = False

    def __init__(self, store: SnapshotTokenStore) -> None:
        if not callable(getattr(store, "snapshot", None)):
            raise ActionTokenError()
        self._store = store
        self._lock = RLock()
        self._revoked: set[str] = set()

    @contextmanager
    def guard(self):
        """Hold local revocation fencing across lookup and the old atomic consume."""
        with self._lock:
            yield

    def lookup(self, digest: str) -> TokenMetadata | None:
        validate_digest(digest)
        with self._lock:
            try:
                records = self._store.snapshot()
            except Exception:
                raise ActionTokenError() from None
            if not isinstance(records, tuple) or any(not isinstance(item, ActionTokenRecord) for item in records):
                raise ActionTokenError()
            for record in records:
                if hmac.compare_digest(record.digest, digest):
                    return TokenMetadata(record, revoked=digest in self._revoked)
            return None

    def revoke(self, digest: str) -> None:
        validate_digest(digest)
        with self._lock:
            self._revoked.add(digest)


def lookup_guard(lookup: TokenMetadataLookup):
    """The memory reference exposes a guard; a durable host supplies its own transaction guard."""
    factory = getattr(lookup, "guard", None)
    return factory() if callable(factory) else nullcontext()


@dataclass(frozen=True)
class TokenClickResult:
    consumption: TokenConsumption | None = field(default=None, repr=False)
    refresh_needed: bool = False
    message: str = ""
    operation_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.refresh_needed) is not bool or (
            self.consumption is not None and not isinstance(self.consumption, TokenConsumption)
        ):
            raise ActionTokenError()
        if self.operation_id is not None and (
            not isinstance(self.operation_id, str)
            or re.fullmatch(r"feishu-card:[a-f0-9]{64}", self.operation_id) is None
        ):
            raise ActionTokenError()
        if self.refresh_needed:
            if self.consumption is not None or self.message != EXPIRED_CARD_MESSAGE or self.operation_id is None:
                raise ActionTokenError()
        elif self.message or (self.consumption is not None and self.operation_id != self.consumption.operation_id):
            raise ActionTokenError()

    @property
    def should_execute(self) -> bool:
        return self.consumption is not None and not self.refresh_needed and self.consumption.should_execute

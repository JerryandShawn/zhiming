"""Brain-28 K3 TTL policy; callback fields remain 待对照飞书官方文档核实。"""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta
from types import MappingProxyType

from mingjing_core.timekit.clock import Clock, FrozenClock

from .action_token_contracts import (
    ActionTokenClaim,
    ActionTokenError,
    IssuedActionToken,
    utc,
)
from .action_token_refresh_v2 import (
    EXPIRED_CARD_MESSAGE,
    MemoryTokenMetadataLookup,
    TokenClickResult,
    TokenMetadata,
    TokenMetadataLookup,
    lookup_guard,
)
from .action_token_store import ActionTokenStore
from .action_tokens import ActionTokenService, _operation_id, _token_digest

TTL_BY_KIND = MappingProxyType(
    {
        "question": timedelta(hours=24),
        "decision": timedelta(hours=24),
        "memory_receipt": timedelta(hours=24),
        "brief": timedelta(hours=24),
        "delete_memory": timedelta(minutes=15),
        "delete_source": timedelta(minutes=15),
        "apply_organize": timedelta(minutes=15),
        "apply_organization": timedelta(minutes=15),
    }
)

__all__ = [
    "EXPIRED_CARD_MESSAGE",
    "K3TokenService",
    "MemoryTokenMetadataLookup",
    "TTL_BY_KIND",
    "TokenClickResult",
    "TokenMetadata",
    "TokenMetadataLookup",
    "ttl_for_kind",
]


def ttl_for_kind(kind: str, *, asserted_action: str | None = None) -> timedelta:
    # kind is the actual dispatch action, not the visual card category. No arbitrary TTL override exists.
    if type(kind) is not str or kind not in TTL_BY_KIND:
        raise ActionTokenError()
    if asserted_action is not None and (type(asserted_action) is not str or asserted_action != kind):
        raise ActionTokenError()
    return TTL_BY_KIND[kind]


def _same_claim(first: ActionTokenClaim, second: ActionTokenClaim) -> bool:
    checks = [
        hmac.compare_digest(getattr(first, key).encode("utf-8"), getattr(second, key).encode("utf-8"))
        for key in first.__dataclass_fields__
    ]
    return all(checks)


class K3TokenService:
    def __init__(self, store: ActionTokenStore, *, clock: Clock, lookup: TokenMetadataLookup) -> None:
        if not callable(getattr(lookup, "lookup", None)) or not callable(getattr(clock, "now", None)):
            raise ActionTokenError()
        # Reuse the old service as the only issue/atomic-consume authority; no second usage ledger is created.
        ActionTokenService(store, clock=clock)
        self._store, self._clock, self._lookup = store, clock, lookup

    def _service(self, now: datetime) -> ActionTokenService:
        return ActionTokenService(self._store, clock=FrozenClock(now))

    def issue(
        self,
        *,
        owner_id: str,
        subject_id: str,
        open_id: str,
        kind: str,
        entity_id: str,
        payload_fingerprint: str,
        asserted_action: str | None = None,
    ) -> IssuedActionToken:
        duration = ttl_for_kind(kind, asserted_action=asserted_action)
        try:
            now = utc(self._clock.now())
            return self._service(now).issue(
                owner_id=owner_id,
                subject_id=subject_id,
                open_id=open_id,
                kind=kind,
                entity_id=entity_id,
                payload_fingerprint=payload_fingerprint,
                ttl=duration,
            )
        except Exception:
            raise ActionTokenError() from None

    def consume(
        self,
        raw_token: str,
        *,
        owner_id: str,
        subject_id: str,
        open_id: str,
        kind: str,
        entity_id: str,
        payload_fingerprint: str,
        asserted_action: str | None = None,
    ) -> TokenClickResult:
        duration = ttl_for_kind(kind, asserted_action=asserted_action)
        claim = ActionTokenClaim(owner_id, subject_id, open_id, kind, entity_id, payload_fingerprint)
        digest = _token_digest(raw_token)
        try:
            with lookup_guard(self._lookup):
                metadata = self._lookup.lookup(digest)
                now = utc(self._clock.now())
                self._validate_metadata(metadata, digest, claim, duration, now)
                record = metadata.record
                if now >= record.expires_at:
                    return TokenClickResult(
                        refresh_needed=True, message=EXPIRED_CARD_MESSAGE, operation_id=record.operation_id
                    )
                result = self._service(now).consume(
                    raw_token,
                    owner_id=owner_id,
                    subject_id=subject_id,
                    open_id=open_id,
                    kind=kind,
                    entity_id=entity_id,
                    payload_fingerprint=payload_fingerprint,
                )
                return TokenClickResult(consumption=result, operation_id=result.operation_id)
        except Exception:
            raise ActionTokenError() from None

    @staticmethod
    def _validate_metadata(
        metadata: TokenMetadata | None, digest: str, claim: ActionTokenClaim, duration: timedelta, now: datetime
    ) -> None:
        if not isinstance(metadata, TokenMetadata) or not metadata.active or metadata.revoked:
            raise ActionTokenError()
        record = metadata.record
        if not hmac.compare_digest(record.digest, digest) or not _same_claim(record.claim, claim):
            raise ActionTokenError()
        if record.operation_id != _operation_id(claim) or record.expires_at - record.created_at != duration:
            raise ActionTokenError()
        if now < record.created_at:
            raise ActionTokenError()

"""Offline action capabilities; callback field mapping is deliberately separate from card JSON."""

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta

from mingjing_core.timekit.clock import Clock

from .action_token_contracts import (
    ActionTokenClaim,
    ActionTokenError,
    ActionTokenRecord,
    IssuedActionToken,
    TokenConsumption,
    utc,
)
from .action_token_store import ActionTokenStore, MemoryActionTokenStore

__all__ = ["ActionTokenError", "ActionTokenService", "IssuedActionToken", "MemoryActionTokenStore", "TokenConsumption"]


def _token_digest(raw_token: str) -> str:
    if not isinstance(raw_token, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}", raw_token) is None:
        raise ActionTokenError()
    return hashlib.sha256(("mingjing-card-v1:" + raw_token).encode("ascii")).hexdigest()


def _operation_id(claim: ActionTokenClaim) -> str:
    # The same logical entity/revision payload stays idempotent across duplicate card issuance.
    projection = [claim.owner_id, claim.subject_id, claim.kind, claim.entity_id, claim.payload_fingerprint]
    canonical = json.dumps(projection, ensure_ascii=False, separators=(",", ":")).encode()
    return "feishu-card:" + hashlib.sha256(canonical).hexdigest()


class ActionTokenService:
    def __init__(
        self,
        store: ActionTokenStore,
        *,
        clock: Clock,
        default_ttl: timedelta = timedelta(minutes=15),
        max_ttl: timedelta = timedelta(hours=24),
    ) -> None:
        # 15 minutes is a configurable offline candidate, not a decided product or official platform TTL.
        if (
            not isinstance(default_ttl, timedelta)
            or not isinstance(max_ttl, timedelta)
            or not timedelta(0) < default_ttl <= max_ttl
        ):
            raise ActionTokenError()
        if (
            not callable(getattr(store, "put_if_absent", None))
            or not callable(getattr(store, "consume", None))
            or not callable(getattr(clock, "now", None))
        ):
            raise ActionTokenError()
        self._store = store
        self._clock = clock
        self._default_ttl = default_ttl
        self._max_ttl = max_ttl

    def issue(
        self,
        *,
        owner_id: str,
        subject_id: str,
        open_id: str,
        kind: str,
        entity_id: str,
        payload_fingerprint: str,
        ttl: timedelta | None = None,
    ) -> IssuedActionToken:
        claim = ActionTokenClaim(owner_id, subject_id, open_id, kind, entity_id, payload_fingerprint)
        duration = self._default_ttl if ttl is None else ttl
        if not isinstance(duration, timedelta) or not timedelta(0) < duration <= self._max_ttl:
            raise ActionTokenError()
        now = self._now()
        try:
            expires_at = now + duration
        except OverflowError:
            raise ActionTokenError() from None
        operation = _operation_id(claim)
        for _ in range(3):
            try:
                raw = secrets.token_urlsafe(32)
            except Exception:
                raise ActionTokenError() from None
            record = ActionTokenRecord(_token_digest(raw), claim, now, expires_at, operation)
            try:
                inserted = self._store.put_if_absent(record)
            except Exception:
                raise ActionTokenError() from None
            if type(inserted) is not bool:
                raise ActionTokenError()
            if inserted:
                return IssuedActionToken(raw, expires_at, operation)
        raise ActionTokenError()

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
    ) -> TokenConsumption:
        claim = ActionTokenClaim(owner_id, subject_id, open_id, kind, entity_id, payload_fingerprint)
        digest = _token_digest(raw_token)
        # actor/open_id、按钮 value.t 等外部回调字段待对照飞书官方文档核实；绑定来源必须是已认证服务端上下文。
        try:
            result = self._store.consume(digest, claim, now=self._now())
        except Exception:
            raise ActionTokenError() from None
        if not isinstance(result, TokenConsumption) or any(
            getattr(result, key) != getattr(claim, key)
            for key in ("owner_id", "subject_id", "kind", "entity_id", "payload_fingerprint")
        ):
            raise ActionTokenError()
        if result.operation_id != _operation_id(claim):
            raise ActionTokenError()
        return result

    def _now(self) -> datetime:
        try:
            return utc(self._clock.now())
        except Exception:
            raise ActionTokenError() from None

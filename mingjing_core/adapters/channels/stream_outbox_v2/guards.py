"""Lease capabilities are fenced and receipts are bound to the exact reserved intent."""

import hashlib
import hmac
from datetime import datetime

from .contracts import StreamError, StreamReceipt, StreamState, identity, integer, utc


def token_hash(token: str) -> str:
    identity(token)
    return hashlib.sha256(("stream-outbox-v2:" + token).encode("utf-8")).hexdigest()


def cas(state: StreamState, expected_revision: int) -> None:
    integer(expected_revision)
    if not isinstance(state, StreamState) or expected_revision != state.revision:
        raise StreamError("revision_conflict")


def live_lease(state: StreamState, token: str, fence: int, now: datetime) -> None:
    integer(fence, 1)
    lease = state.lease
    if lease is None or lease.fence != fence or state.fence != fence:
        raise StreamError("lease_fence_conflict")
    if not hmac.compare_digest(lease.token_hash, token_hash(token)):
        raise StreamError("lease_token_conflict")
    if utc(now) >= lease.expires_at:
        raise StreamError("lease_expired")


def bound_receipt(state: StreamState, receipt: StreamReceipt, *, delivered: bool) -> None:
    if not isinstance(receipt, StreamReceipt) or receipt.scope != state.scope:
        raise StreamError("receipt_scope_mismatch")
    intent = state.intent
    if (receipt.operation_id, receipt.payload_fingerprint, receipt.sequence) != (
        intent.operation_id,
        intent.payload_fingerprint,
        intent.sequence,
    ):
        raise StreamError("receipt_intent_mismatch")
    if state.card_id is not None and receipt.card_id != state.card_id:
        raise StreamError("receipt_card_mismatch")
    if state.message_id is not None and receipt.message_id != state.message_id:
        raise StreamError("receipt_message_mismatch")
    if delivered:
        if intent.kind == "create" and (receipt.card_id is None or receipt.message_id is not None):
            raise StreamError("created_card_receipt_required")
        if intent.kind == "send" and receipt.message_id is None:
            raise StreamError("sent_message_receipt_required")
    elif (state.card_id is None and receipt.card_id is not None) or (
        state.message_id is None and receipt.message_id is not None
    ):
        raise StreamError("unsent_evidence_has_unexpected_remote_receipt")

"""Independent fictional inputs for legacy stream capability acceptance."""

from datetime import UTC, datetime, timedelta
from typing import Any

from mingjing_core.adapters.channels.cardkit_contracts import CardCheckpoint, CardScope, fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import (
    FreshnessEvidence,
    StreamReceipt,
    StreamScope,
    StreamState,
    VersionEvidence,
    acknowledge,
    begin_dispatch,
    claim,
    prepare_intent,
    reject,
)
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, 1, 8, tzinfo=UTC)
SCOPE = StreamScope(
    "coverage-owner", "coverage-self", "coverage-outbox", "coverage-run", "coverage-business", "feishu", "ou_fictional"
)
TOKEN = "FICTIONAL_CAPABILITY_SECRET"
TEXT = "虚构流式结果：仅用于离线能力验收。"
DIGEST = "c" * 64
TTL = timedelta(seconds=60)


def payload() -> dict[str, Any]:
    return {
        "schema": "core4.0",
        "message_id": "fictional-assistant",
        "text": TEXT,
        "receipts": [],
        "used_fact_ids": [],
        "used_claim_ids": [],
        "asked": None,
        "options": None,
        "review": {"state": "passed", "reasons": []},
        "usage": {"offline": True},
        "validation": {"status": "validated", "valid": True, "schema": "core4.0"},
        "meta": {
            "core_run": {"run_id": SCOPE.run_id, "operation_id": "fictional-runtime"},
            "subject_id": SCOPE.subject_id,
            "case_ids": [],
            "structural_warnings": [],
        },
    }


def evidence(state: StreamState, purpose: str, clock: FrozenClock) -> FreshnessEvidence:
    body = payload()
    versions = (
        VersionEvidence("source", "fictional-source", "a" * 64, "a" * 64),
        VersionEvidence("dependency", "fictional-profile", "b" * 64, "b" * 64),
    )
    return FreshnessEvidence(
        state.scope,
        state.intent.operation_id,
        state.revision,
        purpose,
        clock.now(),
        f"fictional-{purpose}-{state.revision}",
        "succeeded",
        state.intent.payload_fingerprint,
        fingerprint(body),
        body,
        versions,
        7,
        7,
        tuple((item.category, item.identity, item.expected_hash) for item in versions),
    )


def prepared(kind: str = "create") -> StreamState:
    checkpoint = None
    if kind != "create":
        checkpoint = CardCheckpoint(
            CardScope(SCOPE.owner_id, SCOPE.subject_id, SCOPE.target, SCOPE.business_id),
            phase="created" if kind == "send" else "streaming",
            card_id="fictional-card",
            message_id=None if kind == "send" else "fictional-message",
            initial_fingerprint=DIGEST,
        )
    return prepare_intent(
        SCOPE, operation_id=f"fictional-{kind}", kind=kind, payload_fingerprint=DIGEST, checkpoint=checkpoint
    )


def acquire(
    state: StreamState,
    clock: FrozenClock,
    *,
    token: str = TOKEN,
    proof: FreshnessEvidence | None = None,
    ttl: timedelta = TTL,
) -> StreamState:
    return claim(
        state,
        token=token,
        worker_id="fictional-worker",
        clock=clock,
        ttl=ttl,
        evidence=evidence(state, "claim", clock) if proof is None else proof,
        expected_revision=state.revision,
    ).state


def dispatch(
    state: StreamState, clock: FrozenClock, *, token: str = TOKEN, proof: FreshnessEvidence | None = None
) -> StreamState:
    return begin_dispatch(
        state,
        token=token,
        fence=state.fence,
        expected_revision=state.revision,
        clock=clock,
        evidence=evidence(state, "dispatch", clock) if proof is None else proof,
    )


def receipt(state: StreamState, *, delivered: bool = True) -> StreamReceipt:
    return StreamReceipt(
        state.scope,
        state.intent.operation_id,
        state.intent.payload_fingerprint,
        state.intent.sequence,
        "fictional-card" if delivered and state.intent.kind == "create" else state.card_id,
        "fictional-message" if delivered and state.intent.kind == "send" else state.message_id,
        "fictional-bound-remote-proof",
    )


def settle(state: StreamState, clock: FrozenClock, *, delivered: bool = True) -> StreamState:
    operation = acknowledge if delivered else reject
    return operation(
        state,
        receipt(state, delivered=delivered),
        token=TOKEN,
        fence=state.fence,
        expected_revision=state.revision,
        clock=clock,
    )

"""Independent synthetic Q6 inputs; these proofs have no database authority."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from mingjing_core.adapters.channels.cardkit_contracts import CardCheckpoint, CardScope, fingerprint
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import (
    ReconciliationBinding,
    ReconciliationMerge,
    merge_cardkit_reconciliation,
    namespace_fingerprint,
)
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
from mingjing_core.timekit.clock import Clock

AT = datetime(2026, 10, 21, 1, 2, 3, tzinfo=UTC)
SCOPE = StreamScope("guard-owner", "guard-self", "guard-outbox", "guard-run", "guard-biz", "feishu", "ou_guard")
CARD = CardScope(SCOPE.owner_id, SCOPE.subject_id, SCOPE.target, SCOPE.business_id)
BINDING = ReconciliationBinding(**asdict(SCOPE))
TOKEN = "synthetic-legacy-worker-capability"
BODY = "PRIVATE_SYNTHETIC_LEGACY_BOUNDARY_BODY"
DIGEST = fingerprint({"synthetic": "legacy-guard-payload"})


def envelope() -> dict[str, Any]:
    return {
        "schema": "core4.0",
        "message_id": "guard-message",
        "text": BODY,
        "receipts": [],
        "used_fact_ids": [],
        "used_claim_ids": [],
        "asked": None,
        "options": None,
        "review": {"state": "passed", "reasons": []},
        "usage": {},
        "validation": {"status": "validated", "valid": True, "schema": "core4.0"},
        "meta": {
            "core_run": {"run_id": SCOPE.run_id, "operation_id": "guard-run-operation"},
            "subject_id": SCOPE.subject_id,
            "case_ids": [],
            "structural_warnings": [],
        },
    }


def checkpoint(phase: str = "streaming", reserved: int = 3) -> CardCheckpoint:
    return CardCheckpoint(
        CARD,
        phase=phase,
        version=4,
        card_id="guard-card" if phase != "new" else None,
        message_id="guard-remote" if phase == "streaming" else None,
        last_reserved_sequence=reserved if phase == "streaming" else 0,
        last_acked_sequence=reserved if phase == "streaming" else 0,
        initial_fingerprint=DIGEST if phase != "new" else None,
    )


def prepared(kind: str = "create", *, reserved: int = 3) -> StreamState:
    old = None if kind == "create" else checkpoint("created" if kind == "send" else "streaming", reserved)
    return prepare_intent(SCOPE, operation_id="guard-" + kind, kind=kind, payload_fingerprint=DIGEST, checkpoint=old)


def proof(state: StreamState, purpose: str, clock: Clock, *, body: dict | None = None) -> FreshnessEvidence:
    content = envelope() if body is None else body
    versions = (
        VersionEvidence("source", "guard-user-source", "a" * 64, "a" * 64),
        VersionEvidence("dependency", "guard-profile", "b" * 64, "b" * 64),
    )
    return FreshnessEvidence(
        state.scope,
        state.intent.operation_id,
        state.revision,
        purpose,
        clock.now(),
        "guard-transaction-" + purpose,
        "succeeded",
        state.intent.payload_fingerprint,
        fingerprint(content),
        content,
        versions,
        8,
        8,
        tuple((v.category, v.identity, v.expected_hash) for v in versions),
    )


def acquire(state: StreamState, clock: Clock, evidence: FreshnessEvidence | None = None) -> StreamState:
    return claim(
        state,
        token=TOKEN,
        worker_id="guard-worker",
        clock=clock,
        ttl=timedelta(seconds=60),
        evidence=proof(state, "claim", clock) if evidence is None else evidence,
        expected_revision=state.revision,
    ).state


def dispatch(state: StreamState, clock: Clock, evidence: FreshnessEvidence | None = None) -> StreamState:
    return begin_dispatch(
        state,
        token=TOKEN,
        fence=state.fence,
        expected_revision=state.revision,
        clock=clock,
        evidence=proof(state, "dispatch", clock) if evidence is None else evidence,
    )


def settled(clock: Clock, kind: str = "update", *, refused: bool = False) -> StreamState:
    sent = dispatch(acquire(prepared(kind), clock), clock)
    receipt = StreamReceipt(
        SCOPE,
        sent.intent.operation_id,
        DIGEST,
        sent.intent.sequence,
        "guard-card",
        "guard-remote",
        "guard-definite-refusal" if refused else "guard-bound-ack",
    )
    operation = reject if refused else acknowledge
    return operation(sent, receipt, token=TOKEN, fence=sent.fence, expected_revision=sent.revision, clock=clock)


def merge(current: dict, state: StreamState, *, row: int = 0, old: CardCheckpoint | None = None) -> ReconciliationMerge:
    return merge_cardkit_reconciliation(
        current,
        binding=BINDING,
        current_row_revision=row,
        expected_row_revision=row,
        expected_namespace_fingerprint=namespace_fingerprint(current),
        stream=state,
        checkpoint=old,
    )

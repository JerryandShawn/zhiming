"""Synthetic trusted-host projections for CPU measurements, never remote ACK verification."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.adapters.channels.cardkit_official_v3 import (
    ArtifactEvidence,
    OfficialAck,
    OfficialState,
    PreparedOperation,
    begin_dispatch,
    claim,
    new_state,
    prepare_operation,
    settle_ack,
)
from mingjing_core.adapters.channels.cards_official_v3 import answer_card
from mingjing_core.adapters.channels.stream_outbox_v2 import FreshnessEvidence, StreamScope, VersionEvidence
from mingjing_core.timekit.clock import FrozenClock

TEXT = "这是一段明确合成的已核验完整回答。"
TOKEN = "synthetic_benchmark_lease_token_00000000"


@dataclass(frozen=True)
class Fixture:
    scope: StreamScope
    clock: FrozenClock
    payload: dict[str, Any] = field(repr=False)
    artifact: ArtifactEvidence = field(repr=False)


def fixture() -> Fixture:
    scope = StreamScope("benchmark-owner", "benchmark-self", "outbox", "run", "business", "feishu", "ou_synthetic")
    payload = {
        "schema": "core4.0",
        "message_id": "synthetic-assistant",
        "text": TEXT,
        "receipts": [],
        "used_fact_ids": [],
        "used_claim_ids": [],
        "asked": None,
        "options": None,
        "usage": {},
        "review": {"state": "passed", "reasons": []},
        "validation": {"status": "validated", "valid": True, "schema": "core4.0"},
        "meta": {
            "core_run": {"run_id": "run", "operation_id": "synthetic-run-operation"},
            "subject_id": scope.subject_id,
            "case_ids": [],
            "structural_warnings": [],
        },
    }
    return Fixture(
        scope,
        FrozenClock(datetime(2026, 10, 21, tzinfo=UTC)),
        payload,
        ArtifactEvidence(scope, fingerprint(payload), 1, answer_card(TEXT)),
    )


def freshness(state: OfficialState, context: Fixture, purpose: str) -> FreshnessEvidence:
    inner = state.lease_state
    assert inner is not None
    versions = (
        VersionEvidence("source", "source", "a" * 64, "a" * 64),
        VersionEvidence("dependency", "profile", "b" * 64, "b" * 64),
    )
    return FreshnessEvidence(
        context.scope,
        inner.intent.operation_id,
        inner.revision,
        purpose,
        context.clock.now(),
        "synthetic-host-transaction",
        "succeeded",
        inner.intent.payload_fingerprint,
        fingerprint(context.payload),
        context.payload,
        versions,
        1,
        1,
        tuple((item.category, item.identity, item.expected_hash) for item in versions),
    )


def prepare(state: OfficialState, context: Fixture, kind: str, payload: Any = None) -> PreparedOperation:
    context.clock.advance(timedelta(milliseconds=400))
    return prepare_operation(
        state,
        kind,
        payload,
        operation_id=f"synthetic-{kind}-{state.revision}",
        artifact=context.artifact,
        clock=context.clock,
    )


def dispatch(prepared: PreparedOperation, context: Fixture) -> OfficialState:
    state, request = prepared.state, prepared.request
    assert request is not None
    state = claim(
        state,
        request,
        artifact=context.artifact,
        evidence=freshness(state, context, "claim"),
        token=TOKEN,
        worker_id="synthetic-worker",
        clock=context.clock,
        ttl=timedelta(seconds=30),
        expected_revision=state.revision,
    )
    return begin_dispatch(
        state,
        request,
        artifact=context.artifact,
        evidence=freshness(state, context, "dispatch"),
        token=TOKEN,
        fence=state.lease_state.fence,
        clock=context.clock,
        expected_revision=state.revision,
    )


def acknowledge(state: OfficialState, context: Fixture) -> OfficialState:
    ack = OfficialAck(
        "synthetic_card", None if state.operation.kind == "create" else "synthetic_message", state.operation.sequence
    )
    return settle_ack(
        state,
        ack,
        evidence_ref="synthetic-ack-only",
        token=TOKEN,
        fence=state.lease_state.fence,
        clock=context.clock,
        expected_revision=state.revision,
    )


def open_stream(context: Fixture) -> OfficialState:
    state = new_state(context.scope)
    for kind in ("create", "send"):
        state = acknowledge(dispatch(prepare(state, context, kind), context), context)
    return state

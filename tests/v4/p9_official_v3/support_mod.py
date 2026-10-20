"""Synthetic public-contract fixtures; no transport, storage or credentials are configured."""

from dataclasses import dataclass
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
from mingjing_core.adapters.channels.stream_outbox_v2 import FreshnessEvidence, StreamScope, VersionEvidence
from mingjing_core.timekit.clock import FrozenClock

TOKEN = "synthetic-lease-token-000000000000000000000000"
TEXT = "这是独立规范验收的合成完整回答。"


@dataclass(frozen=True)
class Environment:
    scope: StreamScope
    clock: FrozenClock
    payload: dict[str, Any]
    artifact: ArtifactEvidence


def environment() -> Environment:
    scope = StreamScope(
        "owner-mod", "subject-mod", "outbox-mod", "run-mod", "business-mod", "feishu", "ou_syntheticOwner"
    )
    payload = {
        "schema": "core4.0",
        "message_id": "message-mod",
        "text": TEXT,
        "answer": TEXT,
        "receipts": [],
        "used_fact_ids": [],
        "used_claim_ids": [],
        "asked": None,
        "options": None,
        "review": {"state": "passed", "reasons": []},
        "usage": {"usage_known": False, "offline": True},
        "validation": {"status": "validated", "valid": True, "schema": "core4.0"},
        "meta": {
            "core_run": {"run_id": scope.run_id, "operation_id": "core-operation-mod"},
            "subject_id": scope.subject_id,
            "case_ids": [],
            "structural_warnings": [],
        },
    }
    card = {
        "schema": "2.0",
        "config": {"update_multi": True, "streaming_mode": False, "summary": {"content": "合成最终摘要"}},
        "header": {"title": {"tag": "plain_text", "content": "明镜"}, "template": "carmine"},
        "body": {"elements": [{"tag": "markdown", "element_id": "answer", "content": TEXT}]},
    }
    artifact = ArtifactEvidence(scope, fingerprint(payload), 1, card)
    return Environment(scope, FrozenClock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC)), payload, artifact)


def freshness(state: OfficialState, env: Environment, purpose: str) -> FreshnessEvidence:
    inner = state.lease_state
    assert inner is not None
    versions = (
        VersionEvidence("source", "source-mod", "a" * 64, "a" * 64),
        VersionEvidence("dependency", "dependency-mod", "b" * 64, "b" * 64),
    )
    return FreshnessEvidence(
        env.scope,
        inner.intent.operation_id,
        inner.revision,
        purpose,
        env.clock.now(),
        f"synthetic-transaction-{state.revision}-{purpose}",
        "validated",
        inner.intent.payload_fingerprint,
        fingerprint(env.payload),
        env.payload,
        versions,
        7,
        7,
        tuple((item.category, item.identity, item.expected_hash) for item in versions),
    )


def prepare(state: OfficialState, env: Environment, kind: str, payload: Any = None) -> PreparedOperation:
    return prepare_operation(
        state, kind, payload, operation_id=f"synthetic-{kind}-{state.revision}", artifact=env.artifact, clock=env.clock
    )


def dispatch(prepared: PreparedOperation, env: Environment) -> OfficialState:
    state = prepared.state
    assert prepared.request is not None
    state = claim(
        state,
        prepared.request,
        artifact=env.artifact,
        evidence=freshness(state, env, "claim"),
        token=TOKEN,
        worker_id="worker-mod",
        clock=env.clock,
        ttl=timedelta(seconds=30),
        expected_revision=state.revision,
    )
    assert state.lease_state is not None
    return begin_dispatch(
        state,
        prepared.request,
        artifact=env.artifact,
        evidence=freshness(state, env, "dispatch"),
        token=TOKEN,
        fence=state.lease_state.fence,
        clock=env.clock,
        expected_revision=state.revision,
    )


def acknowledge(state: OfficialState, env: Environment) -> OfficialState:
    assert state.operation is not None and state.lease_state is not None
    kind = state.operation.kind
    ack = OfficialAck(
        card_id="12345",
        message_id=None if kind == "create" else "om_syntheticMessage",
        sequence=state.operation.sequence,
    )
    state = settle_ack(
        state,
        ack,
        evidence_ref="synthetic-remote-ack",
        token=TOKEN,
        fence=state.lease_state.fence,
        clock=env.clock,
        expected_revision=state.revision,
    )
    env.clock.advance(timedelta(milliseconds=500))
    return state


def run_step(state: OfficialState, env: Environment, kind: str, payload: Any = None) -> OfficialState:
    return acknowledge(dispatch(prepare(state, env, kind, payload), env), env)


def open_stream(env: Environment) -> OfficialState:
    state = run_step(new_state(env.scope), env, "create")
    return run_step(state, env, "send")

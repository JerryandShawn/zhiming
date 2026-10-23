"""Full synthetic stream lease lifecycles and crash-to-unknown paths; no transport or persistence."""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint  # noqa: E402
from mingjing_core.adapters.channels.stream_outbox_v2 import (  # noqa: E402
    FreshnessEvidence,
    StreamError,
    StreamReceipt,
    StreamScope,
    VersionEvidence,
    acknowledge,
    begin_dispatch,
    claim,
    fallback_intent,
    next_intent,
    prepare_intent,
    restore_state,
    state_metadata,
)
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

AT = datetime(2026, 10, 21, tzinfo=UTC)
KINDS = ("create", "send", "update", "close")


def fixture(index: int):
    scope = StreamScope(
        "synthetic-lease-owner",
        "self",
        f"outbox-{index}",
        f"run-{index}",
        f"business-{index}",
        "feishu",
        f"ou_synthetic_{index}",
    )
    text = f"合成卡片{index}：确认下一步行动；核对已保存回执，并保留原话依据。" * 4
    payload = {
        "schema": "core4.0",
        "schema_version": "core4.0",
        "message_id": f"message-{index}",
        "text": text,
        "answer": text,
        "receipts": [{"write_status": "saved", "fact_id": "synthetic-fact", "revision": 1}],
        "used_fact_ids": ["synthetic-fact"],
        "used_claim_ids": ["synthetic-claim"],
        "asked": None,
        "options": None,
        "review": {"state": "passed", "reasons": []},
        "usage": {"model_steps": 0, "offline": True, "usage_known": False},
        "validation": {"valid": True, "status": "validated", "schema": "core4.0"},
        "meta": {
            "subject_id": scope.subject_id,
            "case_ids": [],
            "structural_warnings": [],
            "core_run": {"run_id": scope.run_id, "operation_id": f"run-operation-{index}"},
        },
    }
    return scope, FrozenClock(AT), payload


def freshness(state, payload, clock, purpose):
    versions = tuple(
        VersionEvidence(category, key, fingerprint([category, key, 1]), fingerprint([category, key, 1]))
        for category, key in (
            ("source", "source-message"),
            ("source", "source-fact"),
            ("dependency", "profile"),
            ("dependency", "knowledge"),
            ("dependency", "chart"),
        )
    )
    manifest = tuple((item.category, item.identity, item.expected_hash) for item in versions)
    return FreshnessEvidence(
        scope=state.scope,
        operation_id=state.intent.operation_id,
        expected_revision=state.revision,
        purpose=purpose,
        checked_at=clock.now(),
        transaction_id=f"txn-{purpose}-{state.revision}",
        run_status="succeeded",
        intent_payload_fingerprint=state.intent.payload_fingerprint,
        run_payload_fingerprint=fingerprint(payload),
        validated_payload=payload,
        versions=versions,
        expected_source_epoch=1,
        current_source_epoch=1,
        expected_manifest=manifest,
    )


def dispatch(state, payload, clock, token):
    old_revision, old_fence = state.revision, state.fence
    leased = claim(
        state,
        token=token,
        worker_id="synthetic-worker",
        clock=clock,
        ttl=timedelta(seconds=30),
        evidence=freshness(state, payload, clock, "claim"),
        expected_revision=old_revision,
    ).state
    assert leased.phase == "leased" and leased.revision == old_revision + 1 and leased.fence == old_fence + 1
    active = begin_dispatch(
        leased,
        token=token,
        fence=leased.fence,
        expected_revision=leased.revision,
        clock=clock,
        evidence=freshness(leased, payload, clock, "dispatch"),
    )
    assert active.phase == "dispatched" and active.dispatch_fingerprint and active.lease is not None
    assert active.revision == leased.revision + 1 and active.scope == state.scope and active.intent == state.intent
    return active


def receipt(state, index):
    return StreamReceipt(
        state.scope,
        state.intent.operation_id,
        state.intent.payload_fingerprint,
        sequence=state.intent.sequence,
        card_id=f"synthetic-card-{index}" if state.intent.kind == "create" else state.card_id,
        message_id=f"synthetic-remote-message-{index}" if state.intent.kind == "send" else state.message_id,
        evidence_ref=f"synthetic-known-ack-{index}-{state.intent.kind}",
    )


def lifecycle_workload(count: int) -> int:
    completed = 0
    for index in range(count):
        scope, clock, payload = fixture(index)
        token = f"synthetic-lease-{index}"
        state = None
        for kind in KINDS:
            data = {"kind": kind, "body": payload["text"], "business_id": scope.business_id}
            intent = dict(operation_id=f"operation-{index}-{kind}", kind=kind, payload_fingerprint=fingerprint(data))
            state = (
                prepare_intent(scope, **intent)
                if state is None
                else next_intent(state, **intent, expected_revision=state.revision)
            )
            reserved = state.last_reserved_sequence
            state = dispatch(state, payload, clock, token)
            before = state
            state = acknowledge(
                state,
                receipt(state, index),
                token=token,
                fence=state.fence,
                expected_revision=state.revision,
                clock=clock,
            )
            assert state.phase == "acked" and state.revision == before.revision + 1 and state.lease is None
            assert state.card_id == f"synthetic-card-{index}" and state.last_reserved_sequence == reserved
            if kind != "create":
                assert state.message_id == f"synthetic-remote-message-{index}"
            if kind in {"update", "close"}:
                assert state.last_acked_sequence == state.intent.sequence == reserved
            clock.advance(timedelta(milliseconds=400))
        assert state.last_acked_sequence == state.last_reserved_sequence == 2
        assert len(state.history) == 3 and state.fence == 4 and state.attempts == 1
        assert state.intent.kind == "close" and fallback_intent(state) is None
        completed += 1
    return completed


def crash_workload(count: int) -> int:
    rejected = 0
    for index in range(count):
        scope, clock, payload = fixture(index)
        state = prepare_intent(
            scope,
            operation_id=f"crash-operation-{index}",
            kind="create",
            payload_fingerprint=fingerprint({"body": payload["text"], "index": index}),
        )
        state = dispatch(state, payload, clock, f"synthetic-crash-lease-{index}")
        restored = restore_state(state_metadata(state), scope=scope)
        assert restored.phase == "uncertain" and restored.lease is None
        assert restored.revision == state.revision + 1 and restored.intent == state.intent
        assert restored.fence == state.fence and restored.attempts == 1 and fallback_intent(restored) is None
        try:
            claim(
                restored,
                token=f"synthetic-reclaim-{index}",
                worker_id="replacement-worker",
                clock=clock,
                ttl=timedelta(seconds=30),
                evidence=freshness(restored, payload, clock, "claim"),
                expected_revision=restored.revision,
            )
        except StreamError as error:
            assert error.reason_code == "intent_not_claimable"
            rejected += 1
        else:
            raise AssertionError("unknown_dispatch_was_reclaimed")
    assert rejected == count
    return rejected


def sources():
    channel = ROOT / "mingjing_core/adapters/channels"
    streaming = ROOT / "mingjing_core/streaming"
    return [
        *(channel / "stream_outbox_v2").glob("*.py"),
        channel / "cardkit_contracts.py",
        channel / "hermes.py",
        ROOT / "mingjing_core/domain/consultation.py",
        ROOT / "mingjing_core/timekit/clock.py",
        *(streaming / name for name in ("event_payloads.py", "event_nested.py", "public_shapes.py", "json_values.py")),
        Path(__file__),
        ROOT / "tools/mod_week/performance.py",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lifecycles", type=int, default=100)
    parser.add_argument("--crashes", type=int, default=1000)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.lifecycles <= 1000 or not 1 <= args.crashes <= 2000:
        raise ValueError("benchmark_output_exists_or_workload_invalid")
    cases = []
    for name, count, operation in (
        ("full_stream_lifecycle", args.lifecycles, lifecycle_workload),
        ("dispatched_crash_restore_deny_reclaim", args.crashes, crash_workload),
    ):
        print(f"starting {name}: {count} units; 1 warmup + 5 timing samples + separate tracemalloc", flush=True)
        result = measure(f"{name}_{count}", lambda operation=operation, count=count: operation(count))
        result.update(
            unit="one full lifecycle" if operation is lifecycle_workload else "one actual dispatch/crash path",
            fixture_setup_included=True,
            correctness_assertions_included=True,
            freshness_checks_per_unit=8 if operation is lifecycle_workload else 2,
            source_entries_per_check=2,
            dependency_entries_per_check=3,
            simulated_transport_calls=0,
            unit_prepare_clock="FrozenClock 2026-10-21 UTC",
            timing_clock="perf_counter wall seconds; CPU-bound pure Python, not process_time CPU seconds",
        )
        cases.append(result)
        print(
            f"completed {name}: median={result['median_seconds']:.6f}s; "
            f"Python_peak={result['separate_tracemalloc_peak_bytes']} bytes",
            flush=True,
        )
    cases[0].update(
        expected_acked_cards=args.lifecycles,
        expected_operations=args.lifecycles * 4,
        expected_final_sequence=2,
        preparations_included="scope, envelope, manifest, card fingerprints, lease",
    )
    cases[1].update(
        expected_reclaim_refusals=args.crashes,
        expected_unknown_states=args.crashes,
        preparations_included="scope, envelope, manifest, lease, metadata serialization and restore",
    )
    write_report(args.output, cases, sources(), clock=SystemClock())


if __name__ == "__main__":
    main()

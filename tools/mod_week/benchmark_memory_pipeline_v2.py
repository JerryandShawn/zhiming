"""Synthetic source-to-event-to-memory-to-K2-to-archive/undo benchmark; nothing is delivered."""

import argparse
import sys
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.application.followups_contracts import (  # noqa: E402
    FollowupCandidate,
    FollowupScope,
    FollowupSettings,
    ReceptivityState,
)
from mingjing_core.memory2.archive import plan_archives  # noqa: E402
from mingjing_core.memory2.contracts import (  # noqa: E402
    MemoryFact,
    MemoryScope,
    MemorySnapshot,
    MemorySource,
    SourceAnchor,
)
from mingjing_core.memory2.event_time_extended_v2 import absolute_event_candidate_extended  # noqa: E402
from mingjing_core.memory2.guards import authorize_fact  # noqa: E402
from mingjing_core.memory2.mutations import apply_plan, plan_write  # noqa: E402
from mingjing_core.memory2.undo import undo_plan  # noqa: E402
from mingjing_core.scheduling.delivery_contracts import DeliveryRequest  # noqa: E402
from mingjing_core.scheduling.delivery_rules import plan_delivery  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

AT = datetime(2026, 10, 17, 2, tzinfo=UTC)
ZONE = ZoneInfo("Asia/Shanghai")


def fixture(index: int):
    scope = MemoryScope(f"synthetic-pipeline-owner-{index}", "self")
    phrase = "明天下午三点" if index % 2 == 0 else "tomorrow at 3pm"
    text = f"请提醒我：{phrase}参加合成读书会。"
    at = AT + timedelta(days=index)
    source = MemorySource(f"synthetic-source-{index}", scope.owner_id, scope.subject_id, text, at)
    anchor = SourceAnchor(source.id, source.revision, 0, len(text), text)
    fact = MemoryFact(
        f"synthetic-event-{index}",
        scope.owner_id,
        scope.subject_id,
        "event",
        text,
        (source.id,),
        source.at,
        source.at + timedelta(minutes=1),
        anchors=(anchor,),
    )
    return fact, MemorySnapshot(scope, sources=(source,)), FrozenClock(fact.recorded_at)


def project_save_replay(original, snapshot, clock, index):
    source = snapshot.sources[0]
    candidate = absolute_event_candidate_extended(original, snapshot, tz=ZONE.key)
    assert not candidate.needs_clarification and candidate.projected is not None
    expected = (source.at.astimezone(ZONE) + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
    projected = candidate.projected
    assert candidate.original == original and candidate.original_source_text == source.text
    assert candidate.wording.original_text == source.text and candidate.wording.replaced
    assert candidate.normalized_source_text.startswith("请提醒我：") and candidate.normalized_source_text.endswith(
        "参加合成读书会。"
    )
    assert projected.event_at == projected.event_end == expected.astimezone(UTC)
    assert projected.anchors == original.anchors and projected.source_ids == original.source_ids
    assert (
        projected.owner_id == source.owner_id == snapshot.scope.owner_id and projected.subject_id == source.subject_id
    )
    plan = plan_write(snapshot, projected, scope=snapshot.scope, operation_id=f"pipeline-write-{index}", clock=clock)
    assert plan.write_status == "saved" and len(plan.changes) == 1
    outcome = apply_plan(snapshot, plan, clock=clock)
    assert outcome.write_status == "saved" and outcome.snapshot.fact(projected.id) == projected
    replay = apply_plan(outcome.snapshot, plan, clock=clock)
    assert replay.replayed and replay.write_status == "saved" and replay.snapshot == outcome.snapshot
    assert replay.snapshot.sources == snapshot.sources and source.text == original.anchors[0].quote
    return projected, outcome.snapshot


def reminder_plans(fact, snapshot, index):
    authorize_fact(fact, snapshot, snapshot.scope)
    source = snapshot.source(fact.source_ids[0])
    scope = FollowupScope(fact.owner_id, fact.subject_id)
    candidate = FollowupCandidate(
        f"synthetic-reminder-{index}",
        scope.owner_id,
        scope.subject_id,
        "reminder",
        fact.event_at,
        category="synthetic_event",
        text=fact.text,
        explicit_requested="请提醒我" in source.text,
        source_active=source.active,
        source_revoked=source.revoked,
    )
    assert candidate.explicit_requested and source.text == fact.anchors[0].quote
    request = DeliveryRequest(f"pipeline-occurrence-{index}", candidate, fact.event_at)
    settings, receptivity = FollowupSettings(timezone=ZONE.key), ReceptivityState(scope.owner_id, scope.subject_id)
    plans = [
        plan_delivery(request, settings, receptivity, scope=scope, clock=FrozenClock(fact.event_at + offset))
        for offset in (timedelta(microseconds=-1), timedelta(), timedelta(hours=12, microseconds=1))
    ]
    assert [plan.disposition for plan in plans] == ["not_due", "push", "app_inbox"]
    assert all(plan.original_due == fact.event_at and plan.scope == scope for plan in plans)
    assert plans[1].allowed and not plans[2].allowed and plans[2].app_inbox_only
    assert plans[2].reason == "reminder_older_than_twelve_hours"


def archive_restore(fact, snapshot, index):
    before = plan_archives(
        snapshot,
        scope=snapshot.scope,
        clock=FrozenClock(fact.event_end - timedelta(microseconds=1)),
        operation_id=f"pipeline-not-expired-{index}",
    )
    assert not before.changes
    expired_clock = FrozenClock(fact.event_end + timedelta(minutes=1))
    plan = plan_archives(snapshot, scope=snapshot.scope, clock=expired_clock, operation_id=f"pipeline-archive-{index}")
    assert len(plan.changes) == 1 and plan.write_status == "archived"
    archived = apply_plan(snapshot, plan, clock=expired_clock)
    assert archived.write_status == "archived" and archived.snapshot.fact(fact.id).status == "archived"
    assert archived.snapshot.sources == snapshot.sources and archived.snapshot.source(fact.source_ids[0]).active
    outcome = undo_plan(archived.snapshot, plan, operation_id=f"pipeline-undo-archive-{index}")
    assert not outcome.conflicts and outcome.write_status == "undone"
    restored = outcome.snapshot.fact(fact.id)
    assert all(getattr(restored, field.name) == getattr(fact, field.name) for field in fields(MemoryFact))
    assert restored == fact and restored.anchors == fact.anchors and outcome.snapshot.sources == snapshot.sources
    assert not outcome.snapshot.source(fact.source_ids[0]).revoked
    assert outcome.snapshot.revision > archived.snapshot.revision > snapshot.revision
    authorize_fact(restored, outcome.snapshot, snapshot.scope)


def pipeline_workload(count: int) -> int:
    completed = 0
    for index in range(count):
        original, empty, clock = fixture(index)
        fact, saved = project_save_replay(original, empty, clock, index)
        reminder_plans(fact, saved, index)
        archive_restore(fact, saved, index)
        assert empty.facts == () and empty.sources[0].text == original.text
        completed += 1
    return completed


def sources():
    core = ROOT / "mingjing_core"
    return [
        *(core / "memory2").glob("*.py"),
        *(core / "timeparse").glob("*.py"),
        core / "memory/slots.py",
        core / "scheduling/delivery_contracts.py",
        core / "scheduling/delivery_rules.py",
        core / "application/followups_contracts.py",
        core / "application/followups_rules.py",
        core / "timekit/clock.py",
        core / "timekit/calendar_cn.py",
        core / "timekit/almanac.py",
        Path(__file__),
        ROOT / "tools/mod_week/performance.py",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.count <= 500:
        raise ValueError("pipeline_benchmark_output_exists_or_count_invalid")
    print(
        f"starting source-to-undo pipeline: {args.count} independent units; warmup + 5 samples + tracemalloc",
        flush=True,
    )
    result = measure(
        f"full_source_event_memory_reminder_archive_undo_{args.count}", lambda: pipeline_workload(args.count)
    )
    result.update(
        unit="one independent scoped source-to-undo pipeline",
        fixture_setup_included=True,
        correctness_assertions_included=True,
        synthetic_sources_per_unit=1,
        facts_per_unit=1,
        original_anchor_checks=True,
        absolute_event_projection=True,
        q2_plan_write_apply_replay=True,
        k2_delivery_plans_per_unit=3,
        k2_dispositions=["not_due", "push", "app_inbox"],
        archive_apply_undo_all_fact_fields_equal=True,
        original_sources_never_modified=True,
        snapshot_revision_monotonic=True,
        chinese_sources=(args.count + 1) // 2,
        english_sources=args.count // 2,
        timezone=ZONE.key,
        source_reference="FrozenClock source.at, one-minute extraction delay",
        timing_clock="perf_counter wall seconds; CPU-bound pure Python, not process_time CPU seconds",
        outbound_notifications=0,
        profile_lookups=0,
        database_calls=0,
        model_calls=0,
        sequential_units=True,
        retained_concurrent_state=False,
    )
    write_report(args.output, [result], sources(), clock=SystemClock())
    print(
        f"completed pipeline: median={result['median_seconds']:.6f}s; "
        f"Python_peak={result['separate_tracemalloc_peak_bytes']} bytes",
        flush=True,
    )


if __name__ == "__main__":
    main()

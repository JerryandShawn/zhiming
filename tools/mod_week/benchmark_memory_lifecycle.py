"""Synthetic memory write/replay/undo, archive and reflection observations; no persistence."""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.memory2.archive import plan_archives  # noqa: E402
from mingjing_core.memory2.contracts import (  # noqa: E402
    MemoryFact,
    MemoryScope,
    MemorySnapshot,
    MemorySource,
    SourceAnchor,
)
from mingjing_core.memory2.mutations import apply_plan, plan_write  # noqa: E402
from mingjing_core.memory2.reflection import reflection_candidates  # noqa: E402
from mingjing_core.memory2.undo import undo_plan  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = MemoryScope("synthetic", "self")


def fixture(count: int) -> tuple[MemorySnapshot, tuple[MemoryFact, ...]]:
    texts = [f"我报名第{index}次读书分享会" for index in range(count)]
    original = "；".join(texts)
    source = MemorySource("synthetic-source", "synthetic", "self", original, AT)
    facts = tuple(
        MemoryFact(
            f"fact-{index}",
            "synthetic",
            "self",
            "event",
            text,
            (source.id,),
            AT,
            AT,
            anchors=(SourceAnchor(source.id, 1, original.index(text), original.index(text) + len(text), text),),
            event_at=AT,
            event_end=AT + timedelta(days=1),
        )
        for index, text in enumerate(texts)
    )
    return MemorySnapshot(SCOPE, sources=(source,)), facts


def write_replay_undo() -> int:
    snapshot, facts = fixture(100)
    clock, plans = FrozenClock(AT), []
    for index, fact in enumerate(facts):
        plan = plan_write(snapshot, fact, scope=SCOPE, operation_id=f"write-{index}", clock=clock)
        outcome = apply_plan(snapshot, plan, clock=clock)
        assert outcome.write_status == "saved"
        snapshot = outcome.snapshot
        plans.append(plan)
    for plan in plans:
        assert apply_plan(snapshot, plan, clock=clock).replayed
    for index in range(99, 49, -1):
        snapshot = undo_plan(snapshot, plans[index], operation_id=f"undo-{index}").snapshot
    assert sum(fact.status == "active" for fact in snapshot.facts) == 50
    return 250


def archive_and_undo() -> int:
    empty, facts = fixture(1000)
    snapshot = MemorySnapshot(SCOPE, facts=facts, sources=empty.sources)
    clock = FrozenClock(AT + timedelta(days=2))
    plan = plan_archives(snapshot, scope=SCOPE, clock=clock, operation_id="archive-batch")
    assert len(plan.changes) == 1000
    after = apply_plan(snapshot, plan, clock=clock).snapshot
    assert all(fact.status == "archived" for fact in after.facts)
    restored = undo_plan(after, plan, operation_id="undo-batch").snapshot
    assert restored.facts == snapshot.facts and restored.sources == snapshot.sources
    return 1000


def reflection_workload() -> int:
    empty, facts = fixture(1000)
    snapshot = MemorySnapshot(SCOPE, facts=facts, sources=empty.sources)
    proposals = reflection_candidates(snapshot, scope=SCOPE, clock=FrozenClock(AT))
    assert proposals and all(proposal.fact_ids for proposal in proposals)
    assert snapshot.facts == facts
    return 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [
        measure(name, operation)
        for name, operation in (
            ("memory_100_write_100_replay_50_undo", write_replay_undo),
            ("memory_archive_1000_and_restore", archive_and_undo),
            ("memory_reflection_1000_candidates", reflection_workload),
        )
    ]
    sources = [*Path("mingjing_core/memory2").glob("*.py"), Path(__file__)]
    write_report(args.output, cases, sources, clock=SystemClock())
    for result in cases:
        print(result["name"], "median_seconds", result["median_seconds"])


if __name__ == "__main__":
    main()

"""Full synthetic enqueue intent, work plan and eight-section renderer, with independent invalidation workload."""

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.application.reflection_v3 import (  # noqa: E402
    BackgroundPermit,
    ProfileDocument,
    ProfileEntry,
    ReflectionEffects,
    ThreadState,
    plan_reflection_work,
    render_about_me,
    schedule_reflection,
)
from mingjing_core.memory2.contracts import (  # noqa: E402
    MemoryFact,
    MemoryScope,
    MemorySnapshot,
    MemorySource,
    SourceAnchor,
)
from mingjing_core.memory2.reflection import ProfileItem  # noqa: E402
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

FIXTURE = ROOT / "tools/eval/fixtures/mod_20261021/reflection_background_synthetic.json"
SCOPE = MemoryScope("synthetic-perf-owner", "synthetic-perf-self")
AT = datetime(2026, 10, 20, 18, tzinfo=UTC)
ROWS = (
    ("basic", "background"),
    ("background", "background"),
    ("goal", "goal"),
    ("person", "relationship"),
    ("preference", "preference"),
    ("communication", "communication"),
    ("event_missing", "event"),
    ("event_ambiguous", "event"),
    ("event_future", "event"),
    ("event_expired", "event"),
    ("assistant", "note"),
    ("background", "background"),
    ("goal", "goal"),
    ("health", "background"),
)


def pair(index: int, key: str, kind: str, texts: dict[str, str]) -> tuple[MemoryFact, MemorySource]:
    said = AT - timedelta(days=2) if key == "event_expired" else AT - timedelta(hours=1)
    role, body = "assistant" if key == "assistant" else "user", texts[key]
    source = MemorySource(
        f"synthetic-source-{index}",
        SCOPE.owner_id,
        SCOPE.subject_id,
        body,
        said,
        role=role,
        origin="assistant" if role == "assistant" else "current_user",
    )
    anchor = SourceAnchor(source.id, 1, 0, len(body), body)
    kwargs = {}
    if key == "basic":
        kwargs.update(slot="preferred_name", value="小远")
    if key == "event_future":
        kwargs.update(event_at=datetime(2026, 10, 22, 7, tzinfo=UTC), event_end=datetime(2026, 10, 22, 8, tzinfo=UTC))
    if key == "event_expired":
        kwargs.update(event_at=datetime(2026, 10, 19, 7, tzinfo=UTC), event_end=datetime(2026, 10, 19, 8, tzinfo=UTC))
    fact = MemoryFact(
        f"synthetic-fact-{index}",
        SCOPE.owner_id,
        SCOPE.subject_id,
        kind,
        body,
        (source.id,),
        said,
        said,
        anchors=(anchor,),
        origin="assistant_claim" if role == "assistant" else "user",
        **kwargs,
    )
    return fact, source


def arguments(fixture: bytes) -> tuple[dict, ProfileDocument, MemoryFact]:
    texts = json.loads(fixture)["texts"]
    pairs = tuple(pair(index, key, kind, texts) for index, (key, kind) in enumerate(ROWS))
    incoming = pairs[12][0]
    facts = tuple(value for index, (value, _) in enumerate(pairs) if index != 12)
    snapshot = MemorySnapshot(SCOPE, facts, tuple(source for _, source in pairs), revision=3, source_epoch=4)
    thread = ThreadState(
        SCOPE, "synthetic-perf-thread", 2, AT - timedelta(minutes=10), tuple(source.id for _, source in pairs)
    )
    entries = []
    for index, section in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (8, 8)):
        current = pairs[index][0]
        item = ProfileItem(
            f"synthetic-profile-{index}",
            section,
            current.text,
            current.source_ids,
            (current.id,),
            updated_at=AT - timedelta(minutes=30),
            pinned=index == 0,
        )
        entries.append(ProfileEntry(SCOPE, item, 1, current.anchors))
    document = ProfileDocument(SCOPE, 5, 3, 4, tuple(entries))
    values = dict(
        snapshot=snapshot,
        thread=thread,
        scope=SCOPE,
        clock=FrozenClock(AT),
        permit=BackgroundPermit(SCOPE, 1, 1, enabled=True, quota_stopped=False),
    )
    return values, document, incoming


def full_workload(fixture: bytes) -> int:
    for _ in range(100):
        values, document, incoming = arguments(fixture)
        decision = schedule_reflection(**values)
        assert decision.disposition == "enqueue"
        work = plan_reflection_work(
            decision.intent, **values, profile=document, current_profile_revision=5, extracted_candidates=(incoming,)
        )
        view = render_about_me(
            document, snapshot=values["snapshot"], scope=SCOPE, clock=values["clock"], current_profile_revision=5
        )
        assert work.status == "planned" and work.episodes and work.rolling_summary
        assert (
            work.duplicates and work.gaps and work.date_repairs and work.archive_candidates and work.followup_candidates
        )
        assert len(view.sections) == 8 and len([section for section in view.sections if section.lines]) == 7
        assert all(row.mood == row.conclusion == "not_inferred" for row in work.episodes)
        assert work.effects == view.effects == ReflectionEffects()
        assert values["snapshot"].fact(incoming.id) is None and not work.fact_candidates
    return 100


def invalidation_workload(fixture: bytes) -> int:
    for _ in range(1000):
        values, _, _ = arguments(fixture)
        first_source = values["snapshot"].sources[0]
        values["thread"] = replace(values["thread"], source_ids=(first_source.id,))
        old = schedule_reflection(**values).intent
        values["thread"] = replace(values["thread"], processed_sources=old.source_manifest, processed_epoch=4)
        sources = (replace(first_source, revoked=True), *values["snapshot"].sources[1:])
        values["snapshot"] = replace(values["snapshot"], sources=sources, source_epoch=5)
        intent = schedule_reflection(**values).intent
        work = plan_reflection_work(intent, **values)
        assert work.status == "planned" and work.reason == "invalidation_only" and work.invalidations
        assert not work.episodes and work.rolling_summary is None and not work.fact_candidates
        assert not work.profile_proposals and not work.archive_candidates and not work.followup_candidates
        assert work.effects == ReflectionEffects()
    return 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().exists():
        raise ValueError("reflection_performance_output_must_be_new")
    fixture = FIXTURE.read_bytes()
    directories = ("mingjing_core/application/reflection_v3", "mingjing_core/memory2", "mingjing_core/timeparse")
    paths = [file for directory in directories for file in (ROOT / directory).glob("*.py")]
    paths.extend(
        [
            Path(__file__),
            FIXTURE,
            ROOT / "tools/mod_week/performance.py",
            ROOT / "mingjing_core/memory/slots.py",
            ROOT / "mingjing_core/timekit/clock.py",
            ROOT / "mingjing_core/scheduling/recurrence_wall.py",
        ]
    )
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    cases = [
        measure("full_enqueue_work_aboutme_100", lambda: full_workload(fixture)),
        measure("revoked_epoch_invalidation_only_1000", lambda: invalidation_workload(fixture)),
    ]
    for case in cases:
        case["timed_work"] = (
            "Fixture decode; all host projections; source/consent guards; pure paths and output assertions"
        )
        case["excluded_preparation"] = "Module imports, fixture byte read, source hashing, report-file write"
    if before != {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}:
        raise ValueError("reflection_performance_source_changed")
    write_report(args.output, cases, paths, clock=SystemClock())
    for case in cases:
        print(case["name"], case["median_seconds"], case["separate_tracemalloc_peak_bytes"])


if __name__ == "__main__":
    main()

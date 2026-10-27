"""Synthetic vectors exercise real frozen output shapes, never authorization or natural language truth."""

import json
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.application.reflection_v3.effects import ReflectionEffects
from mingjing_core.application.reflection_v3.schedule_contracts import ProcessedSource, ReflectionIntent
from mingjing_core.application.reflection_v3.work_contracts import (
    ArchiveCandidate,
    BoundExcerpt,
    DuplicateCandidate,
    ExtractiveSummary,
    FactCandidate,
    FollowupCandidate,
    GapPriorityCandidate,
    InvalidationCandidate,
    KnowledgeGap,
    ReflectionWorkPlan,
    WorkOmission,
)
from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, SourceAnchor
from mingjing_core.memory2.event_time_extended_v2 import ExtendedEventCandidate
from mingjing_core.memory2.reflection import ReflectionProposal
from mingjing_core.timeparse.contracts import AbsolutizedText, TimeCandidate, TimeRangeResult

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tools/eval/fixtures/mod_20261021/reflection_projection_vectors_synthetic.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _base(index: int) -> tuple[Any, ...]:
    text = DATA["strings"][index % len(DATA["strings"])] or DATA["strings"][0]
    at = datetime(2026, 10, 21, tzinfo=UTC) + timedelta(seconds=index)
    scope = MemoryScope(f"synthetic-owner-{index}", "synthetic-self")
    anchor = SourceAnchor("synthetic-source", 1, 0, len(text), text)
    fact = MemoryFact(
        "synthetic-fact",
        scope.owner_id,
        scope.subject_id,
        "event",
        text,
        (anchor.source_id,),
        at,
        at,
        anchors=(anchor,),
        event_at=at,
        event_end=at,
    )
    candidate = TimeCandidate(at, at, "minute", "point", 0.9, text)
    time = TimeRangeResult(
        at,
        at,
        "minute",
        "point",
        0.9,
        text,
        candidates=(candidate,),
        original_text=text,
        matched_text=text,
        span=(0, len(text)),
    )
    wording = AbsolutizedText(text, text, time, False)
    repair = ExtendedEventCandidate(fact, fact, time, wording, False)
    return scope, fact, anchor, candidate, time, wording, repair


def typed_values(index: int = 0) -> tuple[Any, ...]:
    scope, fact, anchor, candidate, time, wording, repair = _base(index)
    at, text = fact.said_at, fact.text
    source = ProcessedSource(anchor.source_id, 1, "1" * 64)
    intent = ReflectionIntent(
        scope, "synthetic-thread", "synthetic-operation", "2" * 64, "idle", at, 2, 3, 4, 5, (source,)
    )
    excerpt = BoundExcerpt(anchor.source_id, 1, "user", at, anchor)
    summary = ExtractiveSummary("synthetic-summary", scope, intent.thread_id, "episode_candidate", 2, 3, (excerpt,))
    incoming = FactCandidate(fact, "save", False, "synthetic_reason")
    duplicate = DuplicateCandidate(
        (fact.id, "synthetic-fact-2"), fact.source_ids, ((fact.id, 1), ("synthetic-fact-2", 2))
    )
    gap = KnowledgeGap("synthetic-gap", "synthetic_reason", text, (fact.id,), fact.source_ids)
    priority = GapPriorityCandidate(gap.id, 1, 2, fact.source_ids)
    archive = ArchiveCandidate(fact.id, 1, fact.source_ids, at)
    followup = FollowupCandidate(fact.id, 1, fact.source_ids, at, at)
    omission, effects = WorkOmission(fact.id, "synthetic_reason"), ReflectionEffects()
    invalidation = InvalidationCandidate(scope, intent.thread_id, 2, 3, fact.source_ids)
    proposal = ReflectionProposal("synthetic-proposal", 1, "synthetic-title", text, fact.source_ids, (fact.id,), at)
    work = _work(
        intent,
        summary,
        dict(
            fact_candidates=(incoming,),
            duplicates=(duplicate,),
            gaps=(gap,),
            gap_priorities=(priority,),
            date_repairs=(repair,),
            profile_proposals=(proposal,),
            archive_candidates=(archive,),
            followup_candidates=(followup,),
            omissions=(omission,),
            invalidations=(invalidation,),
        ),
    )
    return (
        scope,
        fact,
        anchor,
        proposal,
        repair,
        candidate,
        time,
        wording,
        effects,
        source,
        intent,
        excerpt,
        summary,
        incoming,
        duplicate,
        gap,
        priority,
        archive,
        followup,
        omission,
        invalidation,
        work,
    )


def _work(intent: ReflectionIntent, summary: ExtractiveSummary, values: dict[str, Any]) -> ReflectionWorkPlan:
    return ReflectionWorkPlan(
        intent,
        intent.not_before,
        "planned",
        "synthetic_reason",
        "3" * 64,
        episodes=(summary,),
        rolling_summary=summary,
        warnings=("synthetic_warning",),
        **values,
    )


def vector(index: int) -> Any:
    rng = random.Random(DATA["seed"] + index)
    types = typed_values(index)
    leaves = (
        *DATA["strings"],
        None,
        False,
        True,
        0,
        1,
        -1,
        2**63,
        -0.0,
        rng.uniform(-1000, 1000),
        date(2024, 2, 29),
        *types,
    )

    def nested(depth: int) -> Any:
        if depth == 0 or rng.random() < 0.5:
            return rng.choice(leaves)
        entries = [nested(depth - 1) for _ in range(rng.randrange(4))]
        return rng.choice((entries, tuple(entries), {str(i): item for i, item in enumerate(entries)}))

    shared = [index, {"unicode": DATA["strings"][index % len(DATA["strings"])], "empty": []}]
    zone = ZoneInfo(DATA["zones"][index % len(DATA["zones"])])
    instant = datetime(2026, 11, 1, 5, 30, tzinfo=UTC) + timedelta(minutes=index % 180)
    return {
        "typed": types[index % len(types)],
        "tree": nested(3),
        "shared": (shared, shared),
        "instant": instant.astimezone(zone),
        "empty": ([], {}, (), None),
    }


def mutable_ids(value: Any) -> set[int]:
    if type(value) not in (dict, list):
        return set()
    children = value.values() if type(value) is dict else value
    return {id(value)}.union(*(mutable_ids(child) for child in children))

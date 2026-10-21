"""Synthetic host projections connect public APIs; cached report content is never prefiltered."""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.application.reflection_v3 import (
    BackgroundPermit,
    ProfileDocument,
    ProfileEntry,
    ThreadState,
    schedule_reflection,
)
from mingjing_core.application.reports_v2 import BasisRef, BriefSourceState, ReportRecord, compose_period_report
from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.memory2.mutation_contracts import MutationOutcome, MutationPlan
from mingjing_core.memory2.mutations import apply_plan, plan_write
from mingjing_core.memory2.reflection import ProfileItem
from mingjing_core.timekit.clock import FrozenClock

FIXTURE = Path(__file__).parents[3] / "tools/eval/fixtures/mod_20261021/final_pipeline_synthetic.json"
MATRIX = json.loads(FIXTURE.read_text(encoding="utf-8"))
SCOPE = MemoryScope("synthetic-final-owner", "synthetic-final-self")
FOLLOWUP_SCOPE = FollowupScope(SCOPE.owner_id, SCOPE.subject_id)


@dataclass(frozen=True)
class Pipeline:
    clock: FrozenClock
    source: MemorySource
    incoming: MemoryFact
    plan: MutationPlan
    initial: MemorySnapshot
    saved: MutationOutcome | None
    thread: ThreadState
    permit: BackgroundPermit
    area: str
    timezone: str

    @property
    def snapshot(self) -> MemorySnapshot:
        return self.initial if self.saved is None else self.saved.snapshot


def pipeline(
    body: str,
    at: datetime,
    *,
    area: str = "daily",
    timezone: str = "Asia/Shanghai",
    said_at: datetime | None = None,
    assistant: bool = False,
) -> Pipeline:
    clock = FrozenClock(at)
    said = clock.now() - timedelta(hours=1) if said_at is None else said_at
    source = MemorySource(
        "synthetic-final-source",
        SCOPE.owner_id,
        SCOPE.subject_id,
        body,
        said,
        role="assistant" if assistant else "user",
        origin="system" if assistant else "current_user",
    )
    anchor = SourceAnchor(source.id, source.revision, 0, len(body), body)
    incoming = MemoryFact(
        "synthetic-final-fact",
        SCOPE.owner_id,
        SCOPE.subject_id,
        "note" if assistant else "background",
        body,
        (source.id,),
        said,
        said,
        (anchor,),
        origin="assistant_claim" if assistant else "user",
    )
    initial = MemorySnapshot(SCOPE, sources=(source,), source_epoch=11)
    plan = plan_write(initial, incoming, scope=SCOPE, operation_id="synthetic-final-write", clock=clock)
    saved = None if plan.policy_action == "reject" else apply_plan(initial, plan, clock=clock)
    thread = ThreadState(
        SCOPE, "synthetic-final-thread", 1, min(said, clock.now() - timedelta(minutes=10)), (source.id,)
    )
    return Pipeline(
        clock,
        source,
        incoming,
        plan,
        initial,
        saved,
        thread,
        BackgroundPermit(SCOPE, 1, 1, True, False),
        area,
        timezone,
    )


def profile(value: Pipeline, *, pinned: bool = False, edited: bool = False) -> ProfileDocument:
    snapshot = value.snapshot
    rows = tuple(
        ProfileEntry(
            SCOPE,
            ProfileItem(
                "synthetic-profile:" + fact.id,
                2,
                fact.text,
                fact.source_ids,
                (fact.id,),
                updated_at=value.clock.now(),
                pinned=pinned,
                edited_by_user=edited,
            ),
            1,
            fact.anchors,
        )
        for fact in snapshot.facts
    )
    return ProfileDocument(SCOPE, 5, snapshot.revision, snapshot.source_epoch, rows)


def source_digest(source: MemorySource, epoch: int) -> str:
    # This explicit synthetic host value includes role and ledger generation, beyond message-ID-only caching.
    return fingerprint(
        {
            "owner": source.owner_id,
            "subject": source.subject_id,
            "text": source.text,
            "role": source.role,
            "origin": source.origin,
            "revision": source.revision,
            "at": source.at.isoformat(),
            "epoch": epoch,
        }
    )


def source_states(snapshot: MemorySnapshot, source_ids: tuple[str, ...]) -> tuple[BriefSourceState, ...]:
    return tuple(
        BriefSourceState(
            source.id,
            FollowupScope(source.owner_id, source.subject_id),
            source.revision,
            source_digest(source, snapshot.source_epoch),
            active=source.active,
            revoked=source.revoked or source.optout,
            incognito=source.incognito,
        )
        for sid in source_ids
        if (source := snapshot.source(sid)) is not None
    )


def records(value: Pipeline, view: object) -> tuple[ReportRecord, ...]:
    snapshot, output = value.snapshot, []
    for section in view.sections:
        for line in section.lines:
            fact = snapshot.fact(line.fact_ids[0])
            basis = tuple(
                BasisRef(
                    f"m{index}",
                    sid,
                    snapshot.source(sid).revision,
                    SCOPE.owner_id,
                    SCOPE.subject_id,
                    source_digest(snapshot.source(sid), snapshot.source_epoch),
                    "source:" + sid,
                    "/",
                )
                for index, sid in enumerate(line.source_ids, 1)
            )
            output.append(
                ReportRecord(
                    FOLLOWUP_SCOPE,
                    fact.id,
                    "fact",
                    line.text,
                    fact.said_at,
                    basis,
                    source_states(snapshot, fact.source_ids),
                    area_id=value.area,
                    status=fact.status,
                    valid_from=fact.valid_from,
                    valid_to=fact.valid_to,
                    origin=fact.origin,
                )
            )
    return tuple(output)


def current_records(cached: tuple[ReportRecord, ...], snapshot: MemorySnapshot) -> tuple[ReportRecord, ...]:
    # Keep old content and expected basis intact; only actual current state changes.
    return tuple(
        replace(record, source_states=source_states(snapshot, tuple(ref.source_id for ref in record.basis)))
        for record in cached
    )


def scheduling(value: Pipeline) -> dict:
    return {
        "snapshot": value.snapshot,
        "thread": value.thread,
        "scope": SCOPE,
        "clock": value.clock,
        "permit": value.permit,
        "timezone": value.timezone,
    }


def report(value: Pipeline, cached: tuple[ReportRecord, ...], *, kind: str = "weekly", day: object = None) -> object:
    target = value.clock.now().astimezone(ZoneInfo(value.timezone)).date() if day is None else day
    return compose_period_report(
        scope=FOLLOWUP_SCOPE, kind=kind, day=target, clock=value.clock, timezone=value.timezone, records=cached
    )


def schedule(value: Pipeline) -> object:
    return schedule_reflection(**scheduling(value))

"""Pure extractive reflection planning; every persistence or actual reasoning step remains with the host."""

from dataclasses import replace

from mingjing_core.memory2.contracts import Confirmation, MemoryFact, MemoryScope, MemorySettings, MemorySnapshot
from mingjing_core.memory2.reflection import ReflectionProposal, reflection_candidates
from mingjing_core.timekit.clock import Clock

from .fact_analysis import conflict_gaps, date_candidates, duplicate_candidates, gap
from .fact_candidates import check_extracted_candidates
from .fact_policy import FactOmission, select_facts
from .gaps import prioritize_gaps
from .intent_guard import intent_reason
from .lifecycle import lifecycle_candidates
from .profile_contracts import ProfileDocument
from .profile_guard import current_profile_items
from .schedule_contracts import BackgroundPermit, ReflectionIntent, ThreadState
from .summaries import extractive_summaries
from .validation import dataclass_json, digest, instant
from .work_contracts import ExistingGap, InvalidationCandidate, KnowledgeGap, ReflectionWorkPlan, WorkOmission


def plan_reflection_work(
    intent: ReflectionIntent,
    *,
    snapshot: MemorySnapshot,
    thread: ThreadState,
    scope: MemoryScope,
    clock: Clock,
    permit: BackgroundPermit | None,
    profile: ProfileDocument | None = None,
    current_profile_revision: int | None = None,
    settings: MemorySettings | None = None,
    confirmations: tuple[Confirmation, ...] = (),
    extracted_candidates: tuple[MemoryFact, ...] = (),
    existing_gaps: tuple[ExistingGap, ...] = (),
) -> ReflectionWorkPlan:
    now = instant(clock.now())
    reason = intent_reason(intent, snapshot=snapshot, thread=thread, scope=scope, clock=clock, permit=permit)
    if reason:
        return ReflectionWorkPlan(intent, now, "blocked", reason, digest([intent.operation_id, reason]))
    if not intent.source_manifest:
        invalidation = InvalidationCandidate(
            scope, thread.id, snapshot.revision, snapshot.source_epoch, thread.source_ids
        )
        return ReflectionWorkPlan(
            intent,
            now,
            "planned",
            "invalidation_only",
            digest(dataclass_json(invalidation)),
            invalidations=(invalidation,),
            warnings=("no_authorized_thread_content_invalidation_only",),
        )
    return _plan_current(
        intent,
        snapshot,
        thread,
        scope,
        clock,
        profile,
        current_profile_revision,
        settings,
        confirmations,
        extracted_candidates,
        existing_gaps,
    )


def _plan_current(
    intent: ReflectionIntent,
    snapshot: MemorySnapshot,
    thread: ThreadState,
    scope: MemoryScope,
    clock: Clock,
    profile: ProfileDocument | None,
    current_profile_revision: int | None,
    settings: MemorySettings | None,
    confirmations: tuple[Confirmation, ...],
    extracted_candidates: tuple[MemoryFact, ...],
    existing_gaps: tuple[ExistingGap, ...],
) -> ReflectionWorkPlan:
    now = instant(clock.now())
    facts, omitted = select_facts(snapshot, scope=scope, clock=clock, settings=settings, confirmations=confirmations)
    options = MemorySettings() if settings is None else settings
    incoming, skipped, incoming_gaps = check_extracted_candidates(
        extracted_candidates,
        snapshot=snapshot,
        scope=scope,
        clock=clock,
        settings=options,
        confirmations=confirmations,
        thread_source_ids=thread.source_ids,
        known_facts=facts,
    )
    episodes, rolling = extractive_summaries(intent, snapshot)
    repairs, date_gaps = date_candidates(facts, snapshot, intent.timezone)
    proposed = (*conflict_gaps(facts), *date_gaps, *incoming_gaps, *_slot_gaps(omitted, snapshot))
    gaps, priorities, notices = prioritize_gaps(existing_gaps, proposed, facts, scope)
    archives, followups = lifecycle_candidates(
        facts, snapshot, scope=scope, clock=clock, settings=options, confirmations=confirmations
    )
    proposals, profile_notices = _profile(
        profile, current_profile_revision, facts, snapshot, scope, clock, options, confirmations
    )
    warnings = ("extractive_only_emotion_and_conclusions_not_inferred", *notices, *profile_notices)
    if not extracted_candidates:
        warnings += ("llm_missing_fact_extraction_not_run",)
    result = ReflectionWorkPlan(
        intent,
        now,
        "planned",
        "review_candidates_only",
        "0" * 64,
        episodes,
        rolling,
        incoming,
        duplicate_candidates(facts),
        gaps,
        priorities,
        repairs,
        proposals,
        archives,
        followups,
        (*tuple(WorkOmission(row.fact_id, row.reason) for row in omitted), *skipped),
        warnings,
    )
    return _sealed(result)


def _sealed(result: ReflectionWorkPlan) -> ReflectionWorkPlan:
    payload = dataclass_json(result)
    payload.pop("fingerprint")
    return replace(result, fingerprint=digest(payload))


def _profile(
    document: ProfileDocument | None,
    revision: int | None,
    facts: tuple[MemoryFact, ...],
    snapshot: MemorySnapshot,
    scope: MemoryScope,
    clock: Clock,
    settings: MemorySettings,
    confirmations: tuple[Confirmation, ...],
) -> tuple[tuple[ReflectionProposal, ...], tuple[str, ...]]:
    if document is None:
        return (), ("current_profile_snapshot_not_supplied",)
    _, _, notices = current_profile_items(
        document,
        snapshot=snapshot,
        scope=scope,
        clock=clock,
        current_profile_revision=revision,
        settings=settings,
        confirmations=confirmations,
    )
    if "current_profile_snapshot_required" in notices:
        return (), notices
    # Even a stale pinned item stays protected from background overwrite; rendering still filters its sources.
    current_items = tuple(entry.item for entry in document.entries)
    filtered = replace(snapshot, facts=facts)
    proposals = reflection_candidates(filtered, current_items, scope=scope, clock=clock, chart_summaries=())
    return proposals, notices


def _slot_gaps(omitted: tuple[FactOmission, ...], snapshot: MemorySnapshot) -> tuple[KnowledgeGap, ...]:
    facts = tuple(snapshot.fact(row.fact_id) for row in omitted if row.reason == "multiple_current_single_slot")
    if not facts:
        return ()
    return (
        gap(
            "multiple_current_single_slot",
            "同一项资料有多个当前值，请确认以哪个为准？",
            tuple(fact.id for fact in facts),
            tuple(sorted({sid for fact in facts for sid in fact.source_ids})),
        ),
    )

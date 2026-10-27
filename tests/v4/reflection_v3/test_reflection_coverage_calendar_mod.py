"""Real import, permission and review-state failures remain rejected before reflection candidates appear."""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import pytest

from mingjing_core.application.reflection_v3 import ExistingGap, ReflectionError, ReflectionOperation
from mingjing_core.memory2.contracts import Confirmation, MemoryScope

from .calendar_acceptance_support_mod import SCOPE, bundle, profile, schedule, view, work


def test_candidate_from_another_subject_or_duplicate_candidate_identity_is_refused() -> None:
    original = bundle()
    candidate = original.snapshot.facts[0]
    data = replace(original, snapshot=replace(original.snapshot, facts=()))
    intent = schedule(data).intent
    with pytest.raises(ReflectionError):
        work(data, intent, extracted_candidates=(replace(candidate, subject_id="synthetic-other-subject"),))
    with pytest.raises(ReflectionError):
        work(data, intent, extracted_candidates=(candidate, candidate))


def test_source_from_another_thread_and_unanchored_candidate_are_not_promoted() -> None:
    original = bundle()
    candidate = replace(original.snapshot.facts[0], id="synthetic-incoming")
    other = replace(original.snapshot.sources[0], id="synthetic-other-thread-source")
    snapshot = replace(original.snapshot, facts=(), sources=(*original.snapshot.sources, other))
    data = replace(original, snapshot=snapshot)
    intent = schedule(data).intent
    foreign_thread = replace(candidate, source_ids=(other.id,))
    unanchored = replace(candidate, anchors=())
    for incoming in (foreign_thread, unanchored):
        result = work(data, intent, extracted_candidates=(incoming,))
        assert not result.fact_candidates and any(row.id == incoming.id for row in result.omissions)


@pytest.mark.parametrize("kind", ("note", "assistant_claim", "chart_summary", "chart_interpretation"))
def test_non_user_fact_kinds_are_not_relabelled_as_missing_facts(kind: str) -> None:
    original = bundle()
    incoming = replace(original.snapshot.facts[0], kind=kind)
    data = replace(original, snapshot=replace(original.snapshot, facts=()))
    result = work(data, schedule(data).intent, extracted_candidates=(incoming,))
    assert not result.fact_candidates


def test_current_foreign_confirmation_and_untyped_memory_settings_fail_closed() -> None:
    data = bundle()
    anchor = data.snapshot.facts[0].anchors[0]
    confirmation = Confirmation(
        MemoryScope("synthetic-other-owner", SCOPE.subject_id),
        anchor.source_id,
        anchor.revision,
        anchor.quote_fingerprint,
        frozenset(),
        "granted",
        data.clock.now(),
    )
    intent = schedule(data).intent
    for values in ({"confirmations": (confirmation,)}, {"confirmations": ({},)}, {"settings": {}}):
        with pytest.raises(ReflectionError):
            work(data, intent, **values)


def test_future_recording_and_not_yet_effective_fact_do_not_produce_profile_proposals() -> None:
    original = bundle()
    for changes in (
        {"recorded_at": original.clock.now() + timedelta(seconds=1)},
        {"valid_from": original.clock.now() + timedelta(seconds=1)},
    ):
        data = replace(
            original, snapshot=replace(original.snapshot, facts=(replace(original.snapshot.facts[0], **changes),))
        )
        result = work(data, schedule(data).intent)
        assert not result.profile_proposals and any(row.id == data.snapshot.facts[0].id for row in result.omissions)


def gap(data: Any, **overrides: Any) -> ExistingGap:
    fact = data.snapshot.facts[0]
    row = ExistingGap(SCOPE, "synthetic-gap", 1, (fact.id,), fact.source_ids)
    return replace(row, **overrides)


def test_gap_wrong_scope_or_repeated_identity_never_enters_review_priorities() -> None:
    data = bundle()
    intent = schedule(data).intent
    row = gap(data)
    for values in ((row, row), (replace(row, scope=MemoryScope("synthetic-other", SCOPE.subject_id)),)):
        with pytest.raises(ReflectionError):
            work(data, intent, existing_gaps=values)


@pytest.mark.parametrize(
    "changes", ({"fact_ids": ()}, {"fact_ids": ("synthetic-missing",)}, {"source_ids": ("synthetic-missing",)})
)
def test_gap_with_stale_fact_or_incomplete_sources_does_not_receive_new_priority(changes: dict[str, Any]) -> None:
    data = bundle()
    result = work(data, schedule(data).intent, existing_gaps=(gap(data, **changes),))
    assert not result.gap_priorities


@pytest.mark.parametrize("status", ("asked", "answered", "dismissed"))
def test_already_asked_or_closed_gap_is_not_reopened_or_prioritized(status: str) -> None:
    data = bundle()
    result = work(data, schedule(data).intent, existing_gaps=(gap(data, status=status, mentions=9, blocking=True),))
    assert not result.gap_priorities and not result.gaps
    assert result.effects.notifications == 0


def test_explicit_open_gap_priority_uses_current_bound_sources_and_remains_a_proposal() -> None:
    data = bundle()
    row = gap(data, mentions=9, blocking=True)
    result = work(data, schedule(data).intent, existing_gaps=(row,))
    assert len(result.gap_priorities) == 1
    candidate = result.gap_priorities[0]
    assert (candidate.gap_id, candidate.expected_revision, candidate.priority, candidate.source_ids) == (
        row.id,
        row.revision,
        5,
        row.source_ids,
    )
    assert result.effects.fact_writes == 0 and result.effects.notifications == 0


def test_another_queued_operation_blocks_a_thread_and_duplicate_ledger_is_rejected() -> None:
    data = bundle()
    ledger = ReflectionOperation(SCOPE, data.thread.id, "synthetic-other-operation", "a" * 64)
    result = schedule(data, operations=(ledger,))
    assert result.disposition == "blocked" and result.intent is None
    with pytest.raises(ReflectionError):
        schedule(data, operations=(ledger, ledger))


def test_bad_timezone_and_future_daily_cursor_never_choose_a_silent_schedule() -> None:
    data = bundle()
    with pytest.raises(ReflectionError):
        schedule(data, timezone="Synthetic/Unavailable")
    result = schedule(
        data, thread=replace(data.thread, daily_completed_on=data.thread.daily_completed_on + timedelta(days=1))
    )
    assert result.disposition == "blocked"


@pytest.mark.parametrize(
    "changes",
    (
        {"source_ids": ("synthetic-duplicate", "synthetic-duplicate")},
        {"daily_completed_on": datetime(2026, 10, 21)},
        {"retention_scope": "unknown"},
        {"last_activity_at": datetime(2026, 10, 21)},
        {"processed_epoch": True},
    ),
)
def test_thread_restore_rejects_ambiguous_current_cursor_projection(changes: dict[str, Any]) -> None:
    data = bundle()
    with pytest.raises(ReflectionError):
        schedule(data, thread=replace(data.thread, **changes))


@pytest.mark.parametrize("changes", ({"enabled": 1}, {"revision": True}, {"scope": {}}))
def test_host_permission_restore_does_not_coerce_strings_or_numbers_into_authority(changes: dict[str, Any]) -> None:
    data = bundle()
    with pytest.raises(ReflectionError):
        schedule(data, permit=replace(data.permit, **changes))


def test_untyped_snapshot_or_intent_does_not_produce_partial_work() -> None:
    data = bundle()
    with pytest.raises(ReflectionError):
        schedule(data, snapshot={})
    with pytest.raises(ReflectionError):
        work(data, {})


@pytest.mark.parametrize("changes", ({"origin": "model_asserted"}, {"item": {}}, {"scope": {}}))
def test_profile_import_rejects_unknown_origin_or_untyped_bound_item(changes: dict[str, Any]) -> None:
    data = bundle()
    document = profile(data)
    with pytest.raises(ReflectionError):
        view(data, replace(document, entries=(replace(document.entries[0], **changes),)))


def test_profile_import_cannot_duplicate_items_or_forge_current_document_scope_type() -> None:
    data = bundle()
    document = profile(data)
    with pytest.raises(ReflectionError):
        view(data, replace(document, entries=(document.entries[0], document.entries[0])))
    with pytest.raises(ReflectionError):
        view(data, replace(document, scope={}))


def test_serialized_ledger_does_not_accept_non_hash_fingerprint_or_unknown_status() -> None:
    data = bundle()
    for changes in (
        {"input_fingerprint": "not-a-digest"},
        {"state": "execute-now"},
        {"operation_id": "synthetic\ninvalid"},
    ):
        with pytest.raises(ReflectionError):
            ReflectionOperation(
                SCOPE,
                data.thread.id,
                **({"operation_id": "synthetic-operation", "input_fingerprint": "a" * 64} | changes),
            )

"""A scheduled input is rechecked as a full source dependency before any review-only work."""

from dataclasses import asdict, replace
from datetime import timedelta
from typing import Any

import pytest

from mingjing_core.application.reflection_v3 import ReflectionError
from mingjing_core.memory2.contracts import MemoryScope, MemorySettings, SourceAnchor
from mingjing_core.timekit.clock import FrozenClock

from .calendar_acceptance_support_mod import SCOPE, bundle, profile, schedule, wording, work


def assert_blocked(data: Any, intent: Any, **overrides: Any) -> None:
    try:
        result = work(data, intent, **overrides)
    except ReflectionError as error:
        assert data.snapshot.sources[0].text not in str(error)
        return
    assert result.status == "blocked"
    assert not result.episodes and not result.fact_candidates and not result.profile_proposals
    assert not result.archive_candidates and not result.followup_candidates and result.rolling_summary is None


@pytest.mark.parametrize(
    "change", ("full_suffix", "role", "origin", "at", "revision", "revoke", "active", "incognito", "optout")
)
def test_original_source_change_after_planning_invalidates_old_intent(change: str) -> None:
    data = bundle()
    intent = schedule(data).intent
    source = data.snapshot.sources[0]
    changes = {
        "full_suffix": {"text": source.text + wording("suffix")},
        "role": {"role": "assistant"},
        "origin": {"origin": "legacy_unverified"},
        "at": {"at": source.at - timedelta(seconds=1)},
        "revision": {"revision": source.revision + 1},
        "revoke": {"revoked": True},
        "active": {"active": False},
        "incognito": {"incognito": True},
        "optout": {"optout": True},
    }
    snapshot = replace(data.snapshot, sources=(replace(source, **changes[change]),))
    assert_blocked(data, intent, snapshot=snapshot)


@pytest.mark.parametrize("field", ("revision", "source_epoch"))
def test_snapshot_revision_and_source_epoch_are_dependencies(field: str) -> None:
    data = bundle()
    intent = schedule(data).intent
    assert_blocked(data, intent, snapshot=replace(data.snapshot, **{field: getattr(data.snapshot, field) + 1}))


def test_thread_manifest_cannot_shrink_or_change_after_intent() -> None:
    data = bundle()
    intent = schedule(data).intent
    for changes in ({"source_ids": ()}, {"revision": data.thread.revision + 1}, {"incognito": True}, {"running": True}):
        assert_blocked(data, intent, thread=replace(data.thread, **changes))


@pytest.mark.parametrize("field", ("enabled", "quota_stopped", "active", "current_revision"))
def test_permit_recheck_cannot_use_old_background_permission(field: str) -> None:
    data = bundle()
    intent = schedule(data).intent
    changes = {"enabled": False, "quota_stopped": True, "active": False, "current_revision": 3}
    assert_blocked(data, intent, permit=replace(data.permit, **{field: changes[field]}))


def test_wrong_scope_or_before_not_before_is_blocked_before_outputs() -> None:
    data = bundle()
    intent = schedule(data).intent
    assert_blocked(data, intent, scope=MemoryScope("synthetic-other-owner", SCOPE.subject_id))
    assert_blocked(data, intent, clock=FrozenClock(intent.not_before - timedelta(microseconds=1)))


def test_valid_work_is_stable_extractive_review_only_and_has_no_effects() -> None:
    data = bundle()
    intent = schedule(data).intent
    result, replay = work(data, intent), work(data, intent)
    assert result.status == "planned" and result.fingerprint == replay.fingerprint
    assert result.episodes and result.rolling_summary is not None
    excerpts = [excerpt for episode in result.episodes for excerpt in episode.excerpts]
    assert excerpts
    for excerpt in excerpts:
        source = data.snapshot.source(excerpt.source_id)
        assert excerpt.source_revision == source.revision and excerpt.role == source.role
        assert (
            excerpt.at == source.at and excerpt.anchor.quote == source.text[excerpt.anchor.start : excerpt.anchor.end]
        )
    assert all(episode.mood == "not_inferred" and episode.conclusion == "not_inferred" for episode in result.episodes)
    assert all(type(value) is int and value == 0 for value in asdict(result.effects).values())
    assert data.snapshot.sources[0].text not in repr(result)
    assert all(candidate.action == "proposal" for candidate in result.profile_proposals)


def test_injected_missing_non_sensitive_fact_is_candidate_not_a_save() -> None:
    original = bundle()
    fact = original.snapshot.facts[0]
    data = replace(original, snapshot=replace(original.snapshot, facts=()))
    intent = schedule(data).intent
    result = work(data, intent, extracted_candidates=(fact,))
    assert result.status == "planned" and len(result.fact_candidates) == 1
    assert result.fact_candidates[0].fact == fact and result.fact_candidates[0].policy_action == "save"
    assert result.effects.fact_writes == 0 and data.snapshot.facts == ()


def test_assistant_suggestion_never_enters_user_fact_candidates() -> None:
    original = bundle(text_key="assistant")
    source = replace(original.snapshot.sources[0], role="assistant", origin="assistant")
    candidate = replace(original.snapshot.facts[0], origin="assistant_claim")
    data = replace(original, snapshot=replace(original.snapshot, facts=(), sources=(source,)))
    decision = schedule(data)
    if decision.intent is None:
        assert decision.disposition in {"noop", "blocked"}
        return
    result = work(data, decision.intent, extracted_candidates=(candidate,))
    assert not result.fact_candidates
    assert all(excerpt.role == "assistant" for episode in result.episodes for excerpt in episode.excerpts)
    assert result.effects.fact_writes == 0


@pytest.mark.parametrize("text_key", ("sensitive", "birth", "optout"))
def test_background_extraction_keeps_sensitive_profile_and_optout_gates(text_key: str) -> None:
    original = bundle(text_key=text_key)
    candidate = original.snapshot.facts[0]
    data = replace(original, snapshot=replace(original.snapshot, facts=()))
    decision = schedule(data)
    if decision.intent is None:
        assert decision.disposition in {"noop", "blocked"}
        return
    result = work(data, decision.intent, extracted_candidates=(candidate,), settings=MemorySettings())
    assert all(row.policy_action != "save" for row in result.fact_candidates)
    assert all(row.requires_confirmation for row in result.fact_candidates)
    assert result.effects.fact_writes == 0 and result.effects.profile_writes == 0


@pytest.mark.parametrize("protected", ("pinned", "edited_by_user"))
def test_new_profile_proposals_never_target_a_protected_existing_item(protected: str) -> None:
    original = bundle()
    old_source = original.snapshot.sources[0]
    new_source = replace(old_source, id="synthetic-source-two", text=wording("second"))
    anchor = SourceAnchor(new_source.id, 1, 0, len(new_source.text), new_source.text)
    new_fact = replace(
        original.snapshot.facts[0],
        id="synthetic-fact-two",
        text=new_source.text,
        source_ids=(new_source.id,),
        anchors=(anchor,),
    )
    snapshot = replace(original.snapshot, facts=(*original.snapshot.facts, new_fact), sources=(old_source, new_source))
    thread = replace(original.thread, source_ids=(old_source.id, new_source.id))
    data = replace(original, snapshot=snapshot, thread=thread)
    document = profile(data)
    entry = document.entries[0]
    document = replace(document, entries=(replace(entry, item=replace(entry.item, **{protected: True})),))
    result = work(data, schedule(data).intent, profile=document, current_profile_revision=document.revision)
    assert result.status == "planned"
    assert all(row.target_item_id != entry.item.id for row in result.profile_proposals)
    assert any(entry.item.id in row.protected_item_ids for row in result.profile_proposals)
    assert document.entries[0].item.text == original.snapshot.facts[0].text
    assert result.effects.profile_writes == 0

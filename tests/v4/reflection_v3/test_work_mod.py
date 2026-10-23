"""Real pure module paths; quote extraction is not LLM reflection or an emotion model."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from mingjing_core.application.reflection_v3 import (
    ExistingGap,
    ReflectionEffects,
    ReflectionError,
    plan_reflection_work,
)
from mingjing_core.memory2.contracts import MemoryScope, MemorySettings

from .support_mod import AT, SCOPE, TEXTS, changed_source, context, fact, intent_for, profile


def work(values, **kwargs):
    return plan_reflection_work(intent_for(values), **values, **kwargs)


def test_extractive_episode_and_rolling_summary_preserve_source_roles_and_anchors():
    values = context(fact(), fact(2, "assistant", "note"))
    result = work(values)
    assert result.status == "planned" and result.effects == ReflectionEffects()
    assert len(result.episodes) == 1 and result.rolling_summary is not None
    assert [row.role for row in result.episodes[0].excerpts] == ["user", "assistant"]
    assert result.episodes[0].mood == result.episodes[0].conclusion == "not_inferred"
    for excerpt in result.rolling_summary.excerpts:
        source = values["snapshot"].source(excerpt.source_id)
        assert source.text[excerpt.anchor.start : excerpt.anchor.end] == excerpt.anchor.quote
    assert "llm_missing_fact_extraction_not_run" in result.warnings
    assert all(body not in repr(result) for body in TEXTS.values())


@pytest.mark.parametrize(
    "change",
    [{"revoked": True}, {"revision": 2}, {"text": ""}, {"incognito": True}, {"optout": True}, {"role": "assistant"}],
)
def test_work_revalidates_source_manifest_even_if_host_forgets_epoch(change):
    values = context()
    intent = intent_for(values)
    result = plan_reflection_work(intent, **changed_source(values, **change))
    assert result.status == "blocked" and not result.episodes and not result.profile_proposals


def test_work_revalidates_epoch_thread_activity_and_background_stop():
    values = context()
    intent = intent_for(values)
    for current in (
        {**values, "snapshot": replace(values["snapshot"], source_epoch=5)},
        {**values, "thread": replace(values["thread"], last_activity_at=AT)},
        {**values, "permit": replace(values["permit"], quota_stopped=True)},
    ):
        assert plan_reflection_work(intent, **current).status == "blocked"


def test_foreign_scope_is_a_fixed_controlled_error_without_any_quote():
    values = context()
    foreign = MemoryScope("foreign-owner", SCOPE.subject_id)
    with pytest.raises(ReflectionError) as error:
        plan_reflection_work(replace(intent_for(values), scope=foreign), **values)
    assert TEXTS["background"] not in str(error.value) and "foreign-owner" not in str(error.value)


def test_duplicates_and_opposite_preferences_are_review_candidates_without_mutating_facts():
    values = context(
        fact(1, "background"),
        fact(2, "background"),
        fact(3, "positive", "preference"),
        fact(4, "negative", "preference"),
    )
    before = deepcopy(asdict(values["snapshot"]))
    result = work(values)
    assert len(result.duplicates) == 1 and result.duplicates[0].action == "review_merge_only"
    assert any(row.reason == "possible_conflict" and "以哪个为准" in row.question for row in result.gaps)
    assert asdict(values["snapshot"]) == before and result.effects.fact_writes == 0


def test_missing_absolute_date_repairs_and_ambiguous_time_gap_use_original_source():
    values = context(fact(1, "event_missing", "event"), fact(2, "event_ambiguous", "event"))
    result = work(values)
    assert len(result.date_repairs) == 1 and result.date_repairs[0].projected.event_at is not None
    assert result.date_repairs[0].original_source_text == TEXTS["event_missing"]
    assert any(row.reason == "event_date_requires_clarification" for row in result.gaps)
    assert all(current.event_at is None for current in values["snapshot"].facts)


def test_archive_and_future_followup_are_only_source_bound_review_metadata():
    future = fact(
        1, "event_future", "event", event_at=AT + timedelta(days=1), event_end=AT + timedelta(days=1, hours=1)
    )
    expired = fact(2, "event_expired", "event", event_at=AT - timedelta(hours=2), event_end=AT - timedelta(hours=1))
    values = context(future, expired)
    result = work(values)
    assert len(result.archive_candidates) == len(result.followup_candidates) == 1
    assert result.archive_candidates[0].fact_id == expired[0].id
    assert result.followup_candidates[0].fact_id == future[0].id
    assert values["snapshot"].fact(expired[0].id).status == "active" and result.effects.notifications == 0


@pytest.mark.parametrize("protected", ["pinned", "edited"])
def test_profile_proposals_protect_manual_or_pinned_items_and_never_write(protected):
    values = context(fact(1, "background"), fact(2, "goal", "goal"))
    doc = profile(values["snapshot"], selected=(values["snapshot"].facts[0],), **{protected: True})
    # A protected existing item has different approved wording and must receive suggestions only.
    entry = doc.entries[0]
    doc = replace(doc, entries=(replace(entry, item=replace(entry.item, text=TEXTS["positive"])),))
    result = work(values, profile=doc, current_profile_revision=doc.revision)
    proposal = next(row for row in result.profile_proposals if row.section == 2)
    assert entry.item.id in proposal.protected_item_ids and proposal.target_item_id is None
    assert result.effects.profile_writes == 0 and doc.entries[0].item.text == TEXTS["positive"]


@pytest.mark.parametrize("text_key,action", [("goal", "save"), ("health", "proposal"), ("birth", "profile_confirm")])
def test_injected_missing_fact_candidates_apply_policy_without_saving(text_key, action):
    values = context()
    candidate, source = fact(2, text_key)
    snapshot = replace(values["snapshot"], sources=(*values["snapshot"].sources, source))
    values = {
        **values,
        "snapshot": snapshot,
        "thread": replace(values["thread"], source_ids=(*values["thread"].source_ids, source.id)),
    }
    result = work(values, extracted_candidates=(candidate,))
    assert result.fact_candidates[0].policy_action == action and result.effects.fact_writes == 0
    assert values["snapshot"].fact(candidate.id) is None


@pytest.mark.parametrize("text_key", ["optout", "secret", "assistant"])
def test_forbidden_or_assistant_injected_candidates_never_become_facts(text_key):
    values = context()
    candidate, source = fact(2, text_key, "note" if text_key == "assistant" else "background")
    values = {
        **values,
        "snapshot": replace(values["snapshot"], sources=(*values["snapshot"].sources, source)),
        "thread": replace(values["thread"], source_ids=(*values["thread"].source_ids, source.id)),
    }
    result = work(values, extracted_candidates=(candidate,))
    assert not result.fact_candidates and any(row.id == candidate.id for row in result.omissions)


def test_multiple_current_single_slot_creates_a_gap_instead_of_a_profile_fact():
    values = context(
        fact(1, "basic", slot="preferred_name", value="小远"),
        fact(2, "background", slot="preferred_name", value="小明"),
    )
    result = work(values, profile=profile(values["snapshot"]), current_profile_revision=5)
    assert not result.profile_proposals
    assert any(row.reason == "multiple_current_single_slot" for row in result.gaps)


def test_gap_priority_uses_explicit_inputs_and_never_exceeds_fifteen_open_candidates():
    values = context(fact(1, "event_ambiguous", "event"))
    current = values["snapshot"].facts[0]
    existing = tuple(
        ExistingGap(SCOPE, f"gap:synthetic-{index}", 1, (current.id,), current.source_ids, mentions=5, blocking=True)
        for index in range(16)
    )
    result = work(values, existing_gaps=existing)
    assert len(result.gap_priorities) == 15 and all(row.priority == 5 for row in result.gap_priorities)
    assert not result.gaps and "gap_capacity_requires_host_review" in result.warnings


def test_source_policy_does_not_resummarize_sensitive_text_without_explicit_consent():
    values = context(fact(), fact(2, "health"))
    result = work(values, settings=MemorySettings())
    assert all(row.source_id != "synthetic-source-2" for row in result.rolling_summary.excerpts)
    assert any(row.reason == "fact_policy_proposal" for row in result.omissions)


@pytest.mark.parametrize("text_key,kind", [("background", "background"), ("negative", "preference")])
def test_injected_duplicate_or_possible_conflict_does_not_propose_an_automatic_fact(text_key, kind):
    values = context(fact(1, "positive", kind)) if text_key == "negative" else context()
    candidate, source = fact(2, text_key, kind)
    values = {
        **values,
        "snapshot": replace(values["snapshot"], sources=(*values["snapshot"].sources, source)),
        "thread": replace(values["thread"], source_ids=(*values["thread"].source_ids, source.id)),
    }
    result = work(values, extracted_candidates=(candidate,))
    assert not result.fact_candidates
    if text_key == "negative":
        assert result.gaps and result.gaps[0].reason == "possible_conflict"
    else:
        assert any(row.reason == "fact_already_represented" for row in result.omissions)


def test_empty_authorized_manifest_after_epoch_change_can_only_propose_invalidation():
    values = context(fact(), fact(2, "goal", "goal"))
    values["thread"] = replace(values["thread"], source_ids=(values["snapshot"].sources[0].id,))
    old = intent_for(values)
    values = changed_source(values, revoked=True)
    values["snapshot"] = replace(values["snapshot"], source_epoch=5)
    values["thread"] = replace(values["thread"], processed_sources=old.source_manifest, processed_epoch=4)
    result = work(
        values,
        profile=profile(values["snapshot"]),
        current_profile_revision=5,
        extracted_candidates=(fact(3, "goal", "goal")[0],),
    )
    assert result.status == "planned" and result.reason == "invalidation_only" and result.invalidations
    assert not result.episodes and result.rolling_summary is None and not result.fact_candidates
    assert not result.profile_proposals and not result.date_repairs and not result.archive_candidates
    assert not result.followup_candidates and result.effects == ReflectionEffects()

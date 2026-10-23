"""Additional review findings retain original thread/source bindings and never promote conflicting candidates."""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.reflection_v3 import ReflectionError, ReflectionOperation
from mingjing_core.memory2.contracts import SourceAnchor
from mingjing_core.timekit.clock import FrozenClock

from .calendar_acceptance_support_mod import SCOPE, bundle, schedule, wording, work


def test_matching_operation_id_and_fingerprint_cannot_replay_another_thread_ledger() -> None:
    data = bundle()
    intent = schedule(data).intent
    ledger = ReflectionOperation(SCOPE, "synthetic-other-thread", intent.operation_id, intent.input_fingerprint)
    try:
        result = schedule(data, operations=(ledger,))
    except ReflectionError:
        return
    assert result.disposition == "blocked" and result.intent is None and result.replayed is False


@pytest.mark.parametrize("change", ("new_source", "revoke_permit"))
def test_daily_intent_cannot_survive_source_or_permission_change(change: str) -> None:
    now = datetime(2026, 10, 21, 3, tzinfo=ZoneInfo("Asia/Shanghai"))
    data = bundle(now=now, idle=timedelta(minutes=5))
    data = replace(data, thread=replace(data.thread, daily_completed_on=None))
    intent = schedule(data).intent
    assert intent.trigger == "daily"
    options: dict[str, Any] = {}
    if change == "revoke_permit":
        options["permit"] = replace(data.permit, enabled=False)
    else:
        source = replace(data.snapshot.sources[0], id="synthetic-new-source", text=wording("second"))
        options["snapshot"] = replace(data.snapshot, sources=(*data.snapshot.sources, source), revision=5)
        options["thread"] = replace(data.thread, source_ids=(*data.thread.source_ids, source.id), revision=3)
    result = work(data, intent, **options)
    assert result.status == "blocked" and not result.episodes and not result.fact_candidates


def test_epoch_changed_empty_authorized_manifest_cannot_generate_new_content() -> None:
    original = bundle()
    old = schedule(original).intent
    thread = replace(
        original.thread, processed_sources=old.source_manifest, processed_epoch=original.snapshot.source_epoch
    )
    source = replace(original.snapshot.sources[0], revoked=True)
    snapshot = replace(original.snapshot, sources=(source,), source_epoch=original.snapshot.source_epoch + 1)
    data = replace(original, thread=thread, snapshot=snapshot)
    decision = schedule(data)
    if decision.intent is None:
        assert decision.disposition in {"blocked", "noop"}
        return
    assert decision.intent.source_manifest == ()
    result = work(data, decision.intent)
    assert not result.episodes and result.rolling_summary is None
    assert not result.fact_candidates and not result.profile_proposals
    assert not result.date_repairs and not result.archive_candidates and not result.followup_candidates


def incoming_from_second_source(text_key: str, *, original_key: str = "preference") -> tuple[Any, Any]:
    original = bundle(text_key=original_key)
    source = replace(original.snapshot.sources[0], id="synthetic-source-two", text=wording(text_key))
    anchor = SourceAnchor(source.id, source.revision, 0, len(source.text), source.text)
    incoming = replace(
        original.snapshot.facts[0],
        id="synthetic-new-fact",
        text=source.text,
        source_ids=(source.id,),
        anchors=(anchor,),
    )
    snapshot = replace(original.snapshot, sources=(*original.snapshot.sources, source))
    thread = replace(original.thread, source_ids=(*original.thread.source_ids, source.id))
    return replace(original, snapshot=snapshot, thread=thread), incoming


def test_duplicate_original_user_fact_is_not_proposed_again_as_missing() -> None:
    data, incoming = incoming_from_second_source("preference")
    result = work(data, schedule(data).intent, extracted_candidates=(incoming,))
    assert result.status == "planned" and not result.fact_candidates
    assert any(row.id == incoming.id for row in result.omissions)
    assert result.effects.fact_writes == 0


def test_existing_rule_detectable_negation_is_gap_not_ordinary_save_candidate() -> None:
    data, incoming = incoming_from_second_source("coffee_negative", original_key="coffee_positive")
    result = work(data, schedule(data).intent, extracted_candidates=(incoming,))
    assert result.status == "planned" and not result.fact_candidates
    assert result.gaps
    assert any(set(row.source_ids) >= {*incoming.source_ids, *data.snapshot.facts[0].source_ids} for row in result.gaps)
    assert result.effects.fact_writes == 0


def test_daily_work_keeps_original_trigger_when_clock_crosses_next_owner_day() -> None:
    now = datetime(2026, 10, 21, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    data = bundle(now=now, idle=timedelta(minutes=5))
    data = replace(data, thread=replace(data.thread, daily_completed_on=None))
    intent = schedule(data).intent
    assert intent.trigger == "daily"
    result = work(data, intent, clock=FrozenClock(now + timedelta(minutes=2)))
    assert result.status == "planned" and result.intent.trigger == "daily"
    assert result.intent.not_before == intent.not_before

"""Q1→Q2 adapters must preserve original dates and source withdrawal precedence."""

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.memory.retrieval import search
from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.memory2.event_time import absolute_event_candidate
from mingjing_core.memory2.guards import MemoryGuardError
from mingjing_core.memory2.retrieval_projection import search_sources, search_units
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 17, 9, tzinfo=ZoneInfo("Asia/Shanghai"))


def event(text="下周三面试"):
    original = MemorySource("m1", "owner", "self", text, AT)
    fact = MemoryFact(
        "f1",
        "owner",
        "self",
        "event",
        text,
        ("m1",),
        AT,
        AT,
        anchors=(SourceAnchor("m1", 1, 0, len(text), text),),
    )
    return fact, MemorySnapshot(MemoryScope("owner", "self"), facts=(fact,), sources=(original,))


def test_event_time_uses_original_said_at_and_keeps_original_text():
    fact, snapshot = event()
    proposal = absolute_event_candidate(fact, snapshot)
    assert proposal.projected.text == "下周三面试"
    assert proposal.projected.said_at == fact.said_at
    assert proposal.projected.event_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() == "2026-10-21"
    assert snapshot.fact("f1") == fact
    assert fact.event_at is None


@pytest.mark.parametrize("text", ["过几天面试", "今晚凌晨两点开会", "周末或下周三面试", "每周三开会"])
def test_unclear_or_recurring_dates_do_not_become_confirmed_fact(text):
    fact, snapshot = event(text)
    proposal = absolute_event_candidate(fact, snapshot)
    assert proposal.needs_clarification
    assert proposal.projected is None


def test_revocation_wins_over_time_absolutization():
    fact, snapshot = event()
    revoked = replace(snapshot.sources[0], revoked=True)
    with pytest.raises(MemoryGuardError):
        absolute_event_candidate(fact, replace(snapshot, sources=(revoked,)))


def test_model_summary_cannot_change_the_date_in_original_quote():
    fact, snapshot = event()
    model_summary = replace(fact, text="下周四面试")
    proposal = absolute_event_candidate(model_summary, snapshot)
    assert proposal.projected.event_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() == "2026-10-21"
    assert proposal.time.original_text == "下周三面试"


def test_existing_conflicting_absolute_date_requires_confirmation():
    fact, snapshot = event()
    proposal = absolute_event_candidate(replace(fact, event_at=AT), snapshot)
    assert proposal.needs_clarification and proposal.projected is None


def test_projection_excludes_superseded_history_and_retrieval_respects_same_filter():
    fact, snapshot = event()
    old = replace(fact, valid_to=AT + timedelta(days=1), superseded_by="new")
    snapshot = replace(snapshot, facts=(old,))
    clock = FrozenClock(AT + timedelta(days=2))
    assert not search_units(snapshot, clock=clock)
    units = search_units(snapshot, clock=clock, include_history=True)
    assert units[0].valid is False
    assert not search("owner", "self", ["面试"], [], 10, units=units, source_state=search_sources(snapshot))


def test_projection_rechecks_source_not_only_fact_boolean():
    fact, snapshot = event()
    assert search_units(snapshot, clock=FrozenClock(AT))
    snapshot = replace(snapshot, sources=(replace(snapshot.sources[0], revision=2),))
    assert not search_units(snapshot, clock=FrozenClock(AT))


def test_archived_facts_are_explicit_history_but_retired_facts_stay_excluded():
    fact, snapshot = event()
    archived = replace(snapshot, facts=(replace(fact, status="archived"),))
    assert not search_units(archived, clock=FrozenClock(AT))
    historical = search_units(archived, clock=FrozenClock(AT), include_history=True)
    assert len(historical) == 1 and historical[0].valid is False
    retired = replace(snapshot, facts=(replace(fact, status="retired"),))
    assert not search_units(retired, clock=FrozenClock(AT), include_history=True)

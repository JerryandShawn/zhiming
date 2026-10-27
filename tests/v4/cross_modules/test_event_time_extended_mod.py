"""Offline source-to-time adapters preserve provenance and never promote summaries to evidence."""

import random
from dataclasses import fields, replace
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.memory2.event_time_extended_v2 import absolute_event_candidate_extended
from mingjing_core.memory2.guards import MemoryGuardError

ZONE = ZoneInfo("Asia/Shanghai")
AT = datetime(2026, 10, 17, 12, 1, tzinfo=ZONE)
SCOPE = MemoryScope("synthetic-owner", "synthetic-self")


def event(text="明天面试", *, at=AT, summary=None, recorded_at=None):
    source = MemorySource("source", SCOPE.owner_id, SCOPE.subject_id, text, at)
    anchor = SourceAnchor(source.id, source.revision, 0, len(text), text)
    fact = MemoryFact(
        "event",
        SCOPE.owner_id,
        SCOPE.subject_id,
        "event",
        text if summary is None else summary,
        (source.id,),
        at,
        recorded_at or at + timedelta(days=200),
        anchors=(anchor,),
    )
    snapshot = MemorySnapshot(SCOPE, facts=(fact,), sources=(source,))
    return fact, snapshot


def unchanged_evidence(candidate, fact, snapshot):
    assert candidate.original is fact
    assert candidate.projected.anchors == fact.anchors
    assert candidate.projected.source_ids == fact.source_ids
    assert snapshot.sources[0].text[candidate.projected.anchors[0].start : candidate.projected.anchors[0].end] == (
        candidate.projected.anchors[0].quote
    )
    for field in fields(fact):
        if field.name not in {"event_at", "event_end", "text"}:
            assert getattr(candidate.projected, field.name) == getattr(fact, field.name)


CLEAR = [
    (text, offset, tz, summary)
    for text, offset in (
        ("今天面试", 0),
        ("明天面试", 1),
        ("后天面试", 2),
        ("昨天面试", -1),
        ("前天面试", -2),
        ("today interview", 0),
        ("tomorrow interview", 1),
        ("yesterday interview", -1),
    )
    for tz in ("Asia/Shanghai", "Asia/Tokyo", "UTC", "America/Los_Angeles")
    for summary in (None, "模型摘要写着2030年元旦，不能相信该日期")
]


@pytest.mark.parametrize("text,offset,tz,summary", CLEAR)
def test_clear_original_dates_use_source_clock_and_keep_every_source_field(text, offset, tz, summary):
    fact, snapshot = event(text, summary=summary)
    candidate = absolute_event_candidate_extended(fact, snapshot, tz=tz)
    day = snapshot.sources[0].at.astimezone(ZoneInfo(tz)).date() + timedelta(days=offset)
    assert not candidate.needs_clarification and candidate.projected is not None
    assert candidate.projected.event_at == datetime.combine(day, time(), ZoneInfo(tz)).astimezone(UTC)
    assert candidate.projected.event_end == datetime.combine(day + timedelta(days=1), time(), ZoneInfo(tz)).astimezone(
        UTC
    )
    assert candidate.original_source_text == text and candidate.time.original_text == text
    assert day.isoformat() in candidate.normalized_source_text
    assert candidate.projected.text == (summary or candidate.normalized_source_text)
    assert snapshot.fact(fact.id) is fact and fact.event_at is None
    unchanged_evidence(candidate, fact, snapshot)


@pytest.mark.parametrize(
    "text,hour,minute",
    [
        ("明天上午九点面试", 9, 0),
        ("明天下午三点面试", 15, 0),
        ("明天晚上八点半面试", 20, 30),
        ("tomorrow at 9am interview", 9, 0),
        ("tomorrow at 3pm interview", 15, 0),
        ("tomorrow at 20:30 interview", 20, 30),
    ],
)
@pytest.mark.parametrize("tz", ["Asia/Shanghai", "Asia/Tokyo", "UTC", "America/Los_Angeles"])
def test_explicit_clock_point_keeps_equal_start_and_end_instead_of_becoming_an_empty_range(text, hour, minute, tz):
    fact, snapshot = event(text)
    result = absolute_event_candidate_extended(fact, snapshot, tz=tz)
    day = snapshot.sources[0].at.astimezone(ZoneInfo(tz)).date() + timedelta(days=1)
    instant = datetime.combine(day, time(hour, minute), ZoneInfo(tz)).astimezone(UTC)
    assert not result.needs_clarification and result.projected is not None
    assert result.time.kind == "point" and result.projected.event_at == result.projected.event_end == instant
    unchanged_evidence(result, fact, snapshot)


@pytest.mark.parametrize(
    "text",
    [
        "过几天面试",
        "今晚凌晨两点开会",
        "周末或下周三面试",
        "每周三开会",
        "tomorrow or Friday interview",
        "every Monday interview",
        "each week on Friday interview",
        "weekly on Tuesday interview",
        "every 2 weeks on Wednesday",
        "my birthday",
        "生日那天",
        "纪念日",
        "没有任何日期的面试记录",
    ],
)
def test_ambiguous_recurring_profile_dependent_or_missing_dates_do_not_project(text):
    fact, snapshot = event(text)
    result = absolute_event_candidate_extended(fact, snapshot)
    assert result.needs_clarification and result.projected is None
    assert result.original_source_text == text and result.normalized_source_text == text


@pytest.mark.parametrize("component", ["event_at", "event_end", "both"])
def test_any_existing_absolute_component_conflict_is_a_clarification(component):
    fact, snapshot = event()
    kwargs = {}
    if component in {"event_at", "both"}:
        kwargs["event_at"] = AT
    if component in {"event_end", "both"}:
        kwargs["event_end"] = AT + timedelta(hours=1)
    fact = replace(fact, **kwargs)
    result = absolute_event_candidate_extended(fact, snapshot)
    assert result.needs_clarification and result.projected is None
    assert result.reason == "existing_event_time_conflict"
    assert result.time.start != AT and result.original.event_at == kwargs.get("event_at")


@pytest.mark.parametrize("component", ["event_at", "event_end", "both"])
def test_existing_matching_components_allow_completion_without_clearing_any_provenance(component):
    fact, snapshot = event()
    candidate = absolute_event_candidate_extended(fact, snapshot)
    kwargs = {}
    if component in {"event_at", "both"}:
        kwargs["event_at"] = candidate.time.start
    if component in {"event_end", "both"}:
        kwargs["event_end"] = candidate.time.end
    fact = replace(fact, **kwargs)
    repeated = absolute_event_candidate_extended(fact, snapshot)
    assert not repeated.needs_clarification and repeated.projected is not None
    assert repeated.projected.event_at == candidate.time.start and repeated.projected.event_end == candidate.time.end
    unchanged_evidence(repeated, fact, snapshot)


@pytest.mark.parametrize("flag", ["active", "revoked", "incognito", "optout", "revision", "role", "origin"])
def test_source_withdrawal_role_and_revision_guards_precede_date_interpretation(flag):
    fact, snapshot = event()
    changes = {
        "active": False,
        "revoked": True,
        "incognito": True,
        "optout": True,
        "revision": 2,
        "role": "assistant",
        "origin": "imported_unconfirmed",
    }
    bad = replace(snapshot.sources[0], **{flag: changes[flag]})
    with pytest.raises(MemoryGuardError):
        absolute_event_candidate_extended(fact, replace(snapshot, sources=(bad,)))


@pytest.mark.parametrize(
    "text", ["不要保存。明天面试", "密码：synthetic-only，明天面试", "假设我明天面试", "“明天面试”"]
)
def test_optout_secret_hypothetical_and_quoted_claims_remain_blocked(text):
    fact, snapshot = event(text)
    with pytest.raises(MemoryGuardError):
        absolute_event_candidate_extended(fact, snapshot)


@pytest.mark.parametrize(
    "field", ["owner_id", "subject_id", "said_at", "source_valid", "status", "anchors", "source_ids"]
)
def test_fact_scope_source_clock_and_anchor_guards_cannot_be_bypassed(field):
    fact, snapshot = event()
    changes = {
        "owner_id": "other",
        "subject_id": "other",
        "said_at": AT - timedelta(days=1),
        "source_valid": False,
        "status": "archived",
        "anchors": (),
        "source_ids": ("not-present",),
    }
    with pytest.raises(MemoryGuardError):
        absolute_event_candidate_extended(replace(fact, **{field: changes[field]}), snapshot)


def test_only_the_primary_source_quote_may_supply_the_event_date():
    fact, snapshot = event("明天面试", summary="模型摘要却说昨天面试")
    second = MemorySource("secondary", SCOPE.owner_id, SCOPE.subject_id, "下周三复试", AT + timedelta(days=2))
    anchor = SourceAnchor(second.id, 1, 0, len(second.text), second.text)
    fact = replace(fact, source_ids=("source", "secondary"), anchors=(*fact.anchors, anchor))
    result = absolute_event_candidate_extended(fact, replace(snapshot, sources=(*snapshot.sources, second)))
    assert not result.needs_clarification
    assert result.original_source_text == "明天面试"
    assert result.projected.event_at.astimezone(ZONE).date().isoformat() == "2026-10-18"
    assert result.projected.text == fact.text


def test_an_anchor_inside_a_longer_source_does_not_pull_dates_from_outside_it():
    text = "明天面试；背景信息去年搬家。"
    fact, snapshot = event(text, summary="下周三搬家")
    anchor = SourceAnchor("source", 1, 0, 4, "明天面试")
    fact = replace(fact, anchors=(anchor,))
    result = absolute_event_candidate_extended(fact, snapshot)
    assert result.original_source_text == "明天面试"
    assert result.projected.event_at.astimezone(ZONE).date().isoformat() == "2026-10-18"
    assert result.projected.text == fact.text


def test_multiple_primary_anchors_are_not_joined_into_a_new_assertion_for_projection():
    text = "明天面试；下周三复试"
    fact, snapshot = event(text)
    first = SourceAnchor("source", 1, 0, 4, text[:4])
    second = SourceAnchor("source", 1, 5, len(text), text[5:])
    fact = replace(fact, anchors=(second, first))
    result = absolute_event_candidate_extended(fact, snapshot)
    assert result.projected is None and result.needs_clarification
    assert result.reason == "multiple_primary_source_anchors"
    assert result.original.anchors == (second, first)
    assert result.original_source_text == text


def test_non_event_memory_is_not_silently_retyped_to_event_memory():
    fact, snapshot = event()
    with pytest.raises(ValueError, match="event_fact_required"):
        absolute_event_candidate_extended(replace(fact, kind="note"), snapshot)


@pytest.mark.parametrize(
    "text",
    [
        "If I attend tomorrow at 9am, remind me.",
        "Suppose tomorrow is interview day.",
        "Hypothetically, I interview tomorrow.",
        "Maybe I interview tomorrow at 9am.",
        "Perhaps I attend tomorrow at 9am.",
        "For example, I interview tomorrow.",
        "For instance, tomorrow I attend a meeting.",
        "I might attend tomorrow.",
        "I may attend tomorrow.",
        "I may be interviewing tomorrow.",
        "Assuming I attend tomorrow, I will travel.",
        "Let's say I attend tomorrow.",
        "I may not attend tomorrow.",
        "Imagine an interview tomorrow at 9am.",
    ],
)
def test_explicit_english_conditions_examples_and_uncertainty_never_become_actual_events(text):
    fact, snapshot = event(text)
    result = absolute_event_candidate_extended(fact, snapshot)
    assert result.projected is None and result.needs_clarification
    assert result.reason == result.time.reason == "english_nonassertion_source"
    assert result.original_source_text == result.normalized_source_text == text
    assert not result.wording.replaced and result.time.start is None
    assert result.original.anchors == fact.anchors


@pytest.mark.parametrize(
    "text",
    [
        "Interview on May 3, 2027.",
        "my gift arrives tomorrow",
        "I will visit the Mayflower exhibit tomorrow",
        "A shift begins tomorrow",
        "A notification arrives tomorrow",
    ],
)
def test_month_may_and_condition_word_substrings_are_not_nonassertion_markers(text):
    fact, snapshot = event(text)
    result = absolute_event_candidate_extended(fact, snapshot)
    assert result.projected is not None and not result.needs_clarification
    assert result.reason != "english_nonassertion_source"
    assert result.original_source_text == text


def test_condition_outside_the_extracted_anchor_but_in_its_source_fragment_still_blocks_projection():
    text = "If invited, interview tomorrow at 9am."
    fact, snapshot = event(text)
    start = text.index("interview")
    quote = text[start:]
    fact = replace(fact, text=quote, anchors=(SourceAnchor("source", 1, start, len(text), quote),))
    result = absolute_event_candidate_extended(fact, snapshot)
    assert result.reason == "english_nonassertion_source" and result.projected is None
    assert result.original_source_text == result.normalized_source_text == quote


def test_nonassertion_guard_does_not_read_a_different_source_fragment_as_date_evidence():
    text = "If invited I will travel; my gift arrives tomorrow"
    fact, snapshot = event(text)
    start = text.index("my gift")
    quote = text[start:]
    fact = replace(fact, text=quote, anchors=(SourceAnchor("source", 1, start, len(text), quote),))
    result = absolute_event_candidate_extended(fact, snapshot)
    assert result.projected is not None and result.original_source_text == quote


@pytest.mark.parametrize("seed", range(500))
def test_random_source_clock_offsets_and_zone_projections_never_use_recorded_at_or_summary(seed):
    rng = random.Random(seed)
    tz = rng.choice(("Asia/Shanghai", "Asia/Tokyo", "UTC", "America/New_York", "Pacific/Auckland"))
    at = datetime(2026, 10, 17, tzinfo=UTC) + timedelta(minutes=rng.randrange(-400_000, 400_000))
    fact, snapshot = event(
        "tomorrow interview",
        at=at,
        summary="模型摘要猜成2035年元旦",
        recorded_at=at + timedelta(days=rng.randrange(1, 1000)),
    )
    result = absolute_event_candidate_extended(fact, snapshot, tz=tz)
    expected = at.astimezone(ZoneInfo(tz)).date() + timedelta(days=1)
    assert not result.needs_clarification
    assert result.projected.event_at == datetime.combine(expected, time(), ZoneInfo(tz)).astimezone(UTC)
    assert result.projected.event_at != fact.recorded_at and result.projected.text == fact.text
    assert result.projected.event_end == datetime.combine(
        expected + timedelta(days=1), time(), ZoneInfo(tz)
    ).astimezone(UTC)
    unchanged_evidence(result, fact, snapshot)

"""Time, scope and assistant-provenance acceptance; only public projections enter the tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.memory.retrieval import (
    RetrievalConfig,
    SearchSource,
    SearchUnit,
    SourceRef,
    search,
)
from mingjing_core.memory.retrieval_rounds import (
    MessageForRound,
    assistant_claim_candidate,
    build_rounds,
    invalidate_sources,
)

NOW = datetime(2026, 10, 21, 4, tzinfo=UTC)
SINCE, UNTIL = NOW - timedelta(days=7), NOW
OWNER, SUBJECT = "synthetic-owner", "self"


def unit(
    identity: str,
    *,
    kind: str = "fact",
    said_at: datetime = NOW,
    event_at: datetime | None = None,
    origin: str = "user",
    category: str = "background",
) -> SearchUnit:
    return SearchUnit(
        identity,
        OWNER,
        SUBJECT,
        kind,
        "合成面试安排",
        said_at,
        event_at,
        origin,
        (SourceRef("source-" + identity),),
        category=category,
    )


def sources_for(units: tuple[SearchUnit, ...]) -> tuple[SearchSource, ...]:
    return tuple(
        SearchSource(ref.id, item.owner_id, item.subject_id, ref.revision) for item in units for ref in item.source_refs
    )


@pytest.mark.parametrize("vectors", [False, True])
def test_event_time_and_said_time_filters_are_shared_by_both_search_paths(
    vectors: bool,
) -> None:
    inside, outside = SINCE + timedelta(days=2), SINCE - timedelta(days=2)
    records = (
        unit("e-in", kind="event", said_at=outside, event_at=inside),
        unit("e-out", kind="event", said_at=inside, event_at=outside),
        unit("f-event-in", kind="fact_event", said_at=outside, event_at=inside),
        unit("n-in", kind="note", said_at=inside, event_at=outside),
        unit("n-out", kind="note", said_at=outside, event_at=inside),
        unit("f-in", said_at=inside, event_at=outside),
        unit("f-out", said_at=outside, event_at=inside),
    )
    scores = {item.id: 1.0 for item in records} if vectors else None
    found = search(
        OWNER,
        SUBJECT,
        ["面试"],
        ["event", "fact_event", "note", "fact"],
        20,
        SINCE,
        UNTIL,
        units=records,
        source_state=sources_for(records),
        vector_scores=scores,
    )
    assert {hit.unit.id for hit in found} == {"e-in", "f-event-in", "n-in", "f-in"}


@pytest.mark.parametrize("vectors", [False, True])
@pytest.mark.parametrize("kind", ["fact", "note", "event", "fact_event"])
def test_time_interval_is_inclusive_left_and_exclusive_right(vectors: bool, kind: str) -> None:
    records = tuple(
        unit(name, kind=kind, said_at=stamp, event_at=stamp)
        for name, stamp in [
            ("before", SINCE - timedelta(microseconds=1)),
            ("left", SINCE),
            ("last", UNTIL - timedelta(microseconds=1)),
            ("right", UNTIL),
        ]
    )
    scores = {item.id: 0.99 for item in records} if vectors else None
    hits = search(
        OWNER,
        SUBJECT,
        ["面试"],
        [kind],
        20,
        SINCE,
        UNTIL,
        units=records,
        source_state=sources_for(records),
        vector_scores=scores,
    )
    assert {hit.unit.id for hit in hits} == {"left", "last"}


@pytest.mark.parametrize(
    "change",
    [
        {"active": False},
        {"redacted": True},
        {"incognito": True},
        {"revision": 2},
        {"owner_id": "other"},
        {"subject_id": "other"},
    ],
)
@pytest.mark.parametrize("vectors", [False, True])
def test_current_source_authority_precedes_fts_and_vector_scores(change: dict, vectors: bool) -> None:
    record = unit("private", said_at=NOW - timedelta(days=1))
    state = replace(sources_for((record,))[0], **change)
    result = search(
        OWNER,
        SUBJECT,
        ["面试"],
        ["fact"],
        10,
        units=(record,),
        source_state=(state,),
        vector_scores={record.id: 1.0} if vectors else None,
    )
    assert result == ()


@pytest.mark.parametrize("state", [(), (SearchSource("unrelated", OWNER, SUBJECT),)])
def test_missing_source_is_not_authorized_by_a_unit_claim(
    state: tuple[SearchSource, ...],
) -> None:
    record = unit("private")
    assert search(OWNER, SUBJECT, ["面试"], ["fact"], 10, units=(record,), source_state=state) == ()


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("active", "false"),
        ("active", 1),
        ("redacted", 0),
        ("incognito", "false"),
        ("revision", True),
        ("revision", 1.5),
    ],
)
def test_ambiguous_source_primitives_are_rejected(field: str, bad_value: object) -> None:
    with pytest.raises(ValueError):
        replace(SearchSource("s", OWNER, SUBJECT), **{field: bad_value})


@pytest.mark.parametrize("origin", ["assistant", "assistant_claim", "model", "inferred"])
@pytest.mark.parametrize("kind", ["fact", "event", "fact_event"])
def test_assistant_provenance_cannot_be_promoted_to_any_user_fact_kind(origin: str, kind: str) -> None:
    with pytest.raises(ValueError):
        unit("fake-fact", kind=kind, origin=origin)


def test_owner_subject_isolation_holds_even_for_perfect_vector_scores() -> None:
    good = unit("mine")
    records = (
        good,
        replace(unit("other-owner"), owner_id="other"),
        replace(unit("other-subject"), subject_id="other"),
    )
    hits = search(
        OWNER,
        SUBJECT,
        ["面试"],
        ["fact"],
        100,
        units=records,
        source_state=sources_for(records),
        vector_scores={item.id: 1.0 for item in records},
    )
    assert [hit.unit.id for hit in hits] == [good.id]


def fifty_rounds() -> tuple[MessageForRound, ...]:
    result = []
    for index in range(50):
        start = NOW - timedelta(days=50 - index)
        question = "面试前准备什么？" if index == 0 else f"合成轮次{index}的其他问题"
        answer = "建议你准备作品集、确认路线、做一次模拟练习。" if index == 0 else f"合成轮次{index}的其他回答"
        result.extend(
            [
                MessageForRound(f"u{index}", OWNER, SUBJECT, "user", question, start),
                MessageForRound(
                    f"a{index}",
                    OWNER,
                    SUBJECT,
                    "assistant",
                    answer,
                    start + timedelta(minutes=1),
                ),
            ]
        )
    return tuple(result)


def message_sources(messages):
    return tuple(
        SearchSource(
            item.id,
            item.owner_id,
            item.subject_id,
            role=item.role,
            origin="system" if item.role == "assistant" else "current_user",
        )
        for item in messages
    )


def test_fiftieth_round_still_recalls_first_assistant_advice_with_its_own_source() -> None:
    messages = fifty_rounds()
    states = message_sources(messages)
    rounds = build_rounds(messages, source_state=states)
    assert len(rounds) == 50
    note = assistant_claim_candidate(
        messages[1],
        "明镜建议面试前准备作品集、确认路线与模拟练习。",
        source_state=states,
    )
    assert note is not None and note.kind == "note" and note.origin == "assistant_claim" and note.inferred
    assert {ref.id for ref in note.source_refs} == {"a0"}
    hits = search(
        OWNER,
        SUBJECT,
        ["作品集"],
        ["round", "note"],
        10,
        units=(*rounds, note),
        source_state=states,
    )
    assert hits and "a0" in {ref.id for ref in hits[0].unit.source_refs}
    claim_hits = search(OWNER, SUBJECT, ["作品集"], ["note"], 10, units=(note,), source_state=states)
    assert claim_hits[0].attribution == "我上次说过"


@pytest.mark.parametrize(
    "change",
    [{"active": False}, {"redacted": True}, {"incognito": True}, {"revision": 2}],
)
def test_assistant_source_withdrawal_removes_round_and_claim_from_retrieval(
    change: dict,
) -> None:
    messages = fifty_rounds()
    states = message_sources(messages)
    rounds = build_rounds(messages, source_state=states)
    note = assistant_claim_candidate(messages[1], "明镜建议先准备作品集。", source_state=states)
    changed = tuple(replace(state, **change) if state.id == "a0" else state for state in states)
    hits = search(
        OWNER,
        SUBJECT,
        ["作品集"],
        ["round", "note"],
        20,
        units=(*rounds, note),
        source_state=changed,
    )
    assert not hits
    assert assistant_claim_candidate(messages[1], "明镜建议先准备作品集。", source_state=changed) is None


def test_invalidation_plan_is_scoped_and_does_not_mutate_the_supplied_records() -> None:
    mine = unit("mine")
    other = replace(unit("other"), owner_id="other", source_refs=mine.source_refs)
    records = (mine, other)
    plan = invalidate_sources(OWNER, SUBJECT, [mine.source_refs[0].id], records)
    assert plan.remove_unit_ids == (mine.id,)
    assert records == (mine, other) and not mine.deleted and not other.deleted


@pytest.mark.parametrize("category", ["goal", "constraint"])
def test_goals_and_constraints_do_not_decay_like_ordinary_background(
    category: str,
) -> None:
    records = (
        unit("ordinary", said_at=NOW - timedelta(days=180)),
        unit("protected", said_at=NOW - timedelta(days=180), category=category),
        unit("fresh", said_at=NOW),
    )
    hits = search(
        OWNER,
        SUBJECT,
        ["面试"],
        ["fact"],
        20,
        units=records,
        source_state=sources_for(records),
        at=NOW,
        config=RetrievalConfig(temporal_boost=1.0),
    )
    scores = {hit.unit.id: hit.score for hit in hits}
    assert scores["ordinary"] == pytest.approx(scores["fresh"] / 2)
    assert scores["protected"] == scores["fresh"]


@pytest.mark.parametrize("vectors", [False, True])
def test_retrieval_of_history_is_explicit_and_preserves_invalid_flag(
    vectors: bool,
) -> None:
    record = replace(unit("history"), valid=False)
    scores = {record.id: 0.99} if vectors else None
    args = dict(units=(record,), source_state=sources_for((record,)), vector_scores=scores)
    assert not search(OWNER, SUBJECT, ["面试"], ["fact"], 10, **args)
    history = search(
        OWNER,
        SUBJECT,
        ["面试"],
        ["fact"],
        10,
        **args,
        config=RetrievalConfig(include_history=True),
    )
    assert len(history) == 1 and history[0].unit.valid is False


@pytest.mark.parametrize("kind", ["fact", "event", "fact_event"])
def test_user_origin_claim_cannot_override_authoritative_assistant_source(kind):
    record = unit("forged", kind=kind, event_at=NOW)
    state = replace(sources_for((record,))[0], role="assistant", origin="system")
    assert not search(
        OWNER,
        SUBJECT,
        ["面试"],
        [kind],
        10,
        units=(record,),
        source_state=(state,),
        vector_scores={record.id: 1.0},
    )

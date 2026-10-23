"""Source/time filters are shared gates, never bypassed by vector rank or old aliases."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from random import Random

import pytest

from mingjing_core.memory.retrieval import RetrievalConfig, SearchSource, SearchUnit, SourceRef, search
from mingjing_core.memory.retrieval_rounds import (
    MessageForRound,
    assistant_claim_candidate,
    build_rounds,
    invalidate_sources,
)

AT = datetime(2026, 10, 17, tzinfo=UTC)


def unit(ident="fact1", **kwargs):
    return SearchUnit(ident, "owner", "self", "fact", "面试 准备", AT, source_refs=(SourceRef("m1"),), **kwargs)


def source(**kwargs):
    return SearchSource("m1", "owner", "self", **kwargs)


def hits(units, sources, **kwargs):
    return search("owner", "self", ["面试"], [], 10, units=units, source_state=sources, **kwargs)


@pytest.mark.parametrize("change", [{"active": False}, {"redacted": True}, {"incognito": True}, {"revision": 2}])
def test_vector_cannot_restore_invalid_source(change):
    assert not hits([unit()], [source(**change)], vector_scores={"fact1": 1})


def test_missing_or_ambiguous_source_fails_closed():
    assert not hits([unit()], [], vector_scores={"fact1": 1})
    assert not hits([unit()], [source(), source()], vector_scores={"fact1": 1})


def test_scope_is_in_source_and_projection():
    assert not hits([replace(unit(), owner_id="other")], [source()])
    assert not hits([unit()], [replace(source(), subject_id="other")])


@pytest.mark.parametrize("vectors", [None, {"fact1": 1}])
def test_event_filter_uses_event_at_not_said_at(vectors):
    event = replace(unit(), kind="event", event_at=AT + timedelta(days=10))
    assert not hits([event], [source()], since=AT, until=AT + timedelta(days=1), vector_scores=vectors)
    assert hits([event], [source()], since=AT + timedelta(days=10), until=AT + timedelta(days=11))


def test_decay_half_life_and_goal_exception():
    ordinary = hits([unit()], [source()], at=AT + timedelta(days=180))[0]
    goal = hits([replace(unit(), category="goal")], [source()], at=AT + timedelta(days=180))[0]
    assert ordinary.score == pytest.approx(goal.score / 2)


def test_history_is_explicit_and_never_bypasses_revocation():
    old = replace(unit(), valid=False)
    assert not hits([old], [source()])
    assert not hits([old], [source(active=False)], config=RetrievalConfig(include_history=True))
    assert not hits([old], [source()])[0:1]
    assert hits([old], [source()], config=RetrievalConfig(include_history=True))[0].unit.valid is False


def test_notes_cannot_be_constructed_as_user_facts():
    with pytest.raises(ValueError, match="助手"):
        unit(origin="assistant_claim")


def test_citations_are_message_aliases_and_never_ambiguous_between_hits():
    first = unit(alias="〔m2〕")
    second = replace(unit("fact2", alias="〔m2〕"), source_refs=(SourceRef("m2"),))
    selected = hits([first, second], [source(), SearchSource("m2", "owner", "self")])
    assert len({hit.alias for hit in selected}) == 2
    with pytest.raises(ValueError, match="别名"):
        unit(alias="〔c1〕")


def test_rounds_do_not_cross_conversation_boundary():
    user = MessageForRound("m1", "owner", "self", "user", "面试", AT)
    assistant = MessageForRound("m2", "owner", "self", "assistant", "建议你准备简历", AT + timedelta(seconds=1))
    sources = [source(), SearchSource("m2", "owner", "self", role="assistant", origin="system")]
    assert len(build_rounds([user, assistant], source_state=sources)) == 1
    assert not build_rounds([user, replace(assistant, conversation_id="else")], source_state=sources)
    assert not build_rounds([replace(user, incognito=True), assistant], source_state=sources)


def test_claim_is_inferred_note_and_withdrawn_message_invalidates_round_and_claim():
    user = MessageForRound("m1", "owner", "self", "user", "面试", AT)
    reply = MessageForRound("m2", "owner", "self", "assistant", "建议你准备简历", AT + timedelta(seconds=1))
    sources = [source(), SearchSource("m2", "owner", "self", role="assistant", origin="system")]
    claim = assistant_claim_candidate(reply, "明镜建议准备简历", source_state=sources)
    assert claim.kind == "note" and claim.inferred and claim.origin == "assistant_claim"
    rounds = build_rounds([user, reply], source_state=sources)
    plan = invalidate_sources("owner", "self", ["m2"], [claim, *rounds])
    assert set(plan.remove_unit_ids) == {claim.id, rounds[0].id}
    assert not assistant_claim_candidate(reply, "摘要", source_state=[source()])


def test_user_origin_label_cannot_promote_assistant_message_to_fact():
    assistant = replace(source(), role="assistant", origin="system")
    assert not hits([unit()], [assistant], vector_scores={"fact1": 1})


def test_one_thousand_random_source_and_time_properties():
    rng = Random(20261021)
    for _ in range(1000):
        offset = rng.randrange(-100, 100)
        candidate = replace(unit(), kind="event", event_at=AT + timedelta(days=offset))
        valid = bool(rng.randrange(2))
        args = dict(since=AT, until=AT + timedelta(days=10))
        plain = hits([candidate], [source(active=valid)], **args)
        vector = hits([candidate], [source(active=valid)], vector_scores={"fact1": 1}, **args)
        expected = valid and 0 <= offset < 10
        assert bool(plain) == expected == bool(vector)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_bad_vector_scores_rejected(value):
    with pytest.raises(ValueError, match="分数"):
        hits([unit()], [source()], vector_scores={"fact1": value})


def test_naive_and_empty_window_rejected():
    with pytest.raises(ValueError, match="时区"):
        hits([unit()], [source()], since=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="区间"):
        hits([unit()], [source()], since=AT, until=AT)

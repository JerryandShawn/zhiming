"""Profile suggestions and expiration keep authorized originals recoverable."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.memory2.archive import plan_archives
from mingjing_core.memory2.contracts import (
    MemoryFact,
    MemoryScope,
    MemorySnapshot,
    MemorySource,
    SourceAnchor,
)
from mingjing_core.memory2.guards import MemoryGuardError
from mingjing_core.memory2.mutations import apply_plan
from mingjing_core.memory2.reflection import (
    ChartSummary,
    ProfileItem,
    reflection_candidates,
)
from mingjing_core.memory2.scoring import decay_factor, importance_score
from mingjing_core.memory2.undo import undo_plan
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = MemoryScope("owner", "self")
CLOCK = FrozenClock(AT)


def make_fact(text, identity="fact", kind="background", slot=None):
    source = MemorySource("source-" + identity, "owner", "self", text, AT - timedelta(days=1))
    anchor = SourceAnchor(source.id, 1, 0, len(text), text)
    fact = MemoryFact(
        identity,
        "owner",
        "self",
        kind,
        text,
        (source.id,),
        source.at,
        source.at,
        anchors=(anchor,),
        slot=slot,
    )
    return fact, source


def snapshot_for(*facts_and_sources):
    return MemorySnapshot(
        SCOPE,
        facts=tuple(pair[0] for pair in facts_and_sources),
        sources=tuple(pair[1] for pair in facts_and_sources),
    )


def reflect(snapshot, current_items=(), charts=()):
    return reflection_candidates(snapshot, current_items, scope=SCOPE, clock=CLOCK, chart_summaries=charts)


def chart_for(fact, **kwargs):
    chart = ChartSummary(
        "chart",
        SCOPE,
        "扶抑喜用候选木，倾向。",
        (fact.id,),
        fact.source_ids,
        ("〔c1〕", "〔r1〕"),
        "synthetic-rules-v1",
        "leaning",
        True,
    )
    return replace(chart, **kwargs)


def test_all_eight_profile_sections_are_only_source_bound_proposals():
    cases = (
        (1, "请称呼我阿宁。", "background", "preferred_name"),
        (2, "我最近每天骑车上班。", "background", None),
        (3, "我希望今年通过教师资格考试。", "goal", None),
        (4, "我很重视和母亲的关系。", "relationship", None),
        (5, "我不喜欢太甜的奶茶。", "preference", None),
        (6, "请回答得简洁一点。", "communication", None),
        (8, "下次我们跟进作品集完成情况。", "followup", None),
    )
    pairs = [make_fact(text, str(section), kind, slot) for section, text, kind, slot in cases]
    original = snapshot_for(*pairs)
    proposals = reflect(original, charts=(chart_for(pairs[0][0]),))
    assert {item.section for item in proposals} == set(range(1, 9))
    assert all(item.action == "proposal" and item.origin == "reflection" for item in proposals)
    assert all(item.source_ids and item.fact_ids and item.updated_at == AT for item in proposals)
    assert all(set(item.fact_ids) <= {fact.id for fact in original.facts} for item in proposals)
    chart = next(item for item in proposals if item.section == 7)
    assert chart.basis_aliases == ("〔c1〕", "〔r1〕") and chart.stability == "leaning"
    assert chart.method_version == "synthetic-rules-v1"
    assert original == snapshot_for(*pairs)


@pytest.mark.parametrize("protection", ["pinned", "edited_by_user"])
def test_manually_protected_profile_item_is_not_targeted_or_overwritten(protection):
    fact, source = make_fact("我喜欢去森林徒步。", kind="preference")
    original = ProfileItem(
        "manual",
        5,
        "我喜欢安静的路线。",
        pinned=protection == "pinned",
        edited_by_user=protection == "edited_by_user",
    )
    proposal = reflect(snapshot_for((fact, source)), (original,))[0]
    assert proposal.target_item_id != original.id
    assert original.id in proposal.protected_item_ids
    assert original.text == "我喜欢安静的路线。"
    assert proposal.action == "proposal"


def test_duplicate_proposal_is_stable_and_does_not_rewrite_same_profile_text():
    fact, source = make_fact("我喜欢安静地阅读。", kind="preference")
    original = snapshot_for((fact, source))
    first = reflect(original)
    assert first == reflect(original)
    item = ProfileItem("existing", 5, fact.text, fact.source_ids, (fact.id,), updated_at=AT)
    assert reflect(original, (item,)) == ()


@pytest.mark.parametrize(
    "change",
    [
        {"revoked": True},
        {"active": False},
        {"revision": 2},
        {"incognito": True},
        {"optout": True},
        {"role": "assistant"},
        {"owner_id": "other"},
        {"subject_id": "other"},
    ],
)
def test_retracted_or_cross_scope_source_never_generates_profile(change):
    fact, source = make_fact("我希望提升表达能力。", kind="goal")
    assert not reflect(snapshot_for((fact, replace(source, **change))))


@pytest.mark.parametrize(
    "change",
    [
        {"origin": "assistant_claim"},
        {"status": "retired"},
        {"status": "archived"},
        {"status": "deleted"},
        {"source_valid": False},
        {"valid_from": AT + timedelta(seconds=1)},
        {"valid_to": AT},
        {"event_end": AT},
    ],
)
def test_invalid_or_noncurrent_fact_never_generates_profile(change):
    fact, source = make_fact("我希望提升表达能力。", kind="goal")
    assert not reflect(snapshot_for((replace(fact, **change), source)))


@pytest.mark.parametrize(
    "change",
    [
        {"trusted": False},
        {"scope": MemoryScope("other", "self")},
        {"source_ids": ()},
        {"fact_ids": ("missing",)},
        {"basis_aliases": ("〔m1〕",)},
        {"method_version": ""},
        {"stability": "made-up"},
    ],
)
def test_unsupported_chart_summary_never_becomes_section_seven(change):
    fact, source = make_fact("我的命理档案已由本人确认。")
    results = reflect(snapshot_for((fact, source)), charts=(chart_for(fact, **change),))
    assert all(item.section != 7 for item in results)


@pytest.mark.parametrize("kind", ["background", "preference", "event", "concern"])
def test_ordinary_fact_has_180_day_half_life_without_host_timezone(kind):
    fact, _ = make_fact("我会在空闲时画速写。", kind=kind)
    now = FrozenClock(fact.said_at)
    base = importance_score(fact, clock=now)
    now.advance(timedelta(days=180))
    assert decay_factor(fact, clock=now) == pytest.approx(0.5)
    assert importance_score(fact, clock=now) == pytest.approx(base * 0.5)
    now.advance(timedelta(days=180))
    assert importance_score(fact, clock=now) == pytest.approx(base * 0.25)


@pytest.mark.parametrize("kind", ["goal", "constraint"])
def test_goals_and_constraints_do_not_decay(kind):
    fact, _ = make_fact("我希望持续保留这个目标。", kind=kind)
    assert importance_score(fact, clock=FrozenClock(fact.said_at + timedelta(days=1800))) == importance_score(
        fact, clock=FrozenClock(fact.said_at)
    )


def test_pin_raises_importance_and_invalid_source_scores_zero():
    fact, _ = make_fact("我的通勤方式是步行。")
    assert importance_score(replace(fact, pinned=True), clock=CLOCK) > importance_score(fact, clock=CLOCK)
    assert importance_score(replace(fact, source_valid=False, pinned=True), clock=CLOCK) == 0
    assert importance_score(replace(fact, status="retired"), clock=CLOCK) == 0


@pytest.mark.parametrize("deadline_field", ["valid_to", "event_end"])
@pytest.mark.parametrize("offset,archives", [(-1, True), (0, True), (1, False)])
def test_c2_expiration_is_half_open_archival_and_can_be_fully_undone(deadline_field, offset, archives):
    fact, source = make_fact("昨天的作品集面试。", kind="event")
    fact = replace(
        fact,
        **{deadline_field: AT + timedelta(seconds=offset)},
        event_at=AT - timedelta(hours=2),
    )
    original = snapshot_for((fact, source))
    plan = plan_archives(original, scope=SCOPE, clock=CLOCK)
    assert len(plan.changes) == int(archives)
    if archives:
        after = apply_plan(original, plan).snapshot
        archived = after.fact(fact.id)
        assert archived.status == "archived"
        assert replace(archived, status=fact.status, revision=fact.revision) == fact
        assert archived.text == fact.text and archived.source_ids == fact.source_ids
        assert undo_plan(after, plan, operation_id="undo-archive").snapshot.fact(fact.id) == fact
    assert original.fact(fact.id) == fact


def test_a_distant_said_date_or_point_date_alone_is_not_an_invented_expiration():
    fact, source = make_fact("我年轻时学过小提琴。")
    fact = replace(fact, said_at=AT - timedelta(days=500), event_at=AT - timedelta(days=400))
    assert not plan_archives(snapshot_for((fact, source)), scope=SCOPE, clock=CLOCK).changes


def test_expiration_plan_cannot_cross_scope_or_resurrect_revoked_sources():
    fact, source = make_fact("作品集面试结束。", kind="event")
    state = snapshot_for((replace(fact, event_end=AT), replace(source, revoked=True)))
    assert not plan_archives(state, scope=SCOPE, clock=CLOCK).changes
    with pytest.raises(MemoryGuardError):
        plan_archives(state, scope=MemoryScope("other", "self"), clock=CLOCK)

"""Synthetic P5b projections: isolate first, then rank; derived text never creates facts."""

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.organize.source_projection import SearchSource, SearchUnit, SourceRef
from mingjing_core.organize.partition_context_v2 import (
    plan_summary_invalidations,
    project_partition_context,
)
from mingjing_core.organize.partition_context_v2_contracts import (
    PartitionRecord,
    PartitionScope,
)
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = PartitionScope("synthetic-owner", "self", "life:self", "career", "interview")


def fixture(
    index,
    *,
    layer="retrieval",
    space="career",
    topic="interview",
    days=0,
    category="background",
    score=1,
):
    kind = {
        "profile": "fact",
        "summary": "summary",
        "open_topic": "topic",
        "round": "round",
    }.get(layer, "fact")
    source = SearchSource(f"user-{index}", SCOPE.owner_id, SCOPE.subject_id)
    sources = (source,)
    if layer == "round":
        sources += (
            replace(
                source,
                id=f"assistant-{index}",
                role="assistant",
                origin="assistant_claim",
            ),
        )
    unit = SearchUnit(
        f"unit-{index}",
        SCOPE.owner_id,
        SCOPE.subject_id,
        kind,
        f"合成私有正文{index}。不应出现在另一分区的细节",
        AT - timedelta(days=days),
        origin="derived_summary" if layer == "summary" else "user",
        source_refs=tuple(SourceRef(item.id) for item in sources),
        category=category,
        inferred=layer == "summary",
    )
    return PartitionRecord(
        unit, SCOPE.life_thread_id, space, layer, topic, score, f"标题{index}"
    ), sources


def project(fixtures, *, scope=SCOPE, epoch=0, clock=None):
    return project_partition_context(
        tuple(item[0] for item in fixtures),
        tuple(source for _, sources in fixtures for source in sources),
        scope=scope,
        source_epoch=epoch,
        clock=clock or FrozenClock(AT),
    )


def test_constraints_are_global_and_current_space_retrieval_gets_exact_weight():
    values = [
        fixture(1, category="constraint", space="health", score=0),
        fixture(2, score=0.8),
        fixture(3, space="family", score=1),
        fixture(4, space="daily", score=1.3),
    ]
    result = project(values)
    assert [item.id for item in result.constraints] == ["unit-1"]
    assert [(item.id, item.weighted_score) for item in result.retrieval] == [
        ("unit-4", 1.3),
        ("unit-2", pytest.approx(1.2)),
        ("unit-3", 1),
    ]
    assert all(item.id != "unit-1" for item in result.retrieval)


def test_profile_current_details_first_and_other_topics_only_titles():
    result = project(
        [
            fixture(1, layer="profile", space="health"),
            fixture(2, layer="profile"),
            fixture(3, layer="open_topic", space="family"),
            fixture(4, layer="open_topic"),
        ]
    )
    assert [item.id for item in result.profile] == ["unit-2", "unit-1"]
    assert not result.profile[0].abbreviated and "细节" in result.profile[0].text
    assert result.profile[1].text == "合成私有正文1" and result.profile[1].abbreviated
    assert [item.id for item in result.open_topics] == ["unit-4", "unit-3"]
    assert (
        result.open_topics[1].text == "标题3"
        and "私有正文" not in result.open_topics[1].text
    )


def test_current_topic_uses_thirty_complete_rounds_only_in_current_space():
    values = [fixture(index, layer="round", days=index / 100) for index in range(40)]
    values += [
        fixture(100, layer="round", topic="other"),
        fixture(101, layer="round", space="family"),
    ]
    result = project(values)
    assert len(result.rounds) == 30
    assert [item.id for item in result.rounds] == [
        f"unit-{index}" for index in range(29, -1, -1)
    ]
    assert all(len(item.source_refs) == 2 for item in result.rounds)


def test_summary_recent_window_is_exact_seven_days_and_latest_two_per_other_space():
    values = [
        fixture(1, layer="summary", topic=None, days=1),
        fixture(2, layer="summary", topic=None),
        fixture(3, layer="summary", space="health", days=7),
        fixture(4, layer="summary", space="health", days=6),
        fixture(5, layer="summary", space="health", days=5),
        fixture(6, layer="summary", space="family", days=7),
        fixture(7, layer="summary", space="finance", days=7 + 1 / 86400),
    ]
    result = project(values)
    assert [item.id for item in result.current_summary] == ["unit-2"]
    assert [item.id for item in result.recent_elsewhere] == [
        "unit-6",
        "unit-4",
        "unit-5",
    ]
    assert all(
        item.abbreviated and "派生摘要" in item.attribution
        for item in result.recent_elsewhere
    )
    assert "unit-7" in result.omitted_ids


@pytest.mark.parametrize(
    "layer", ["profile", "open_topic", "round", "summary", "retrieval"]
)
@pytest.mark.parametrize(
    "source_change",
    ["active", "redacted", "incognito", "revision", "missing", "owner", "subject"],
)
def test_current_source_guard_applies_before_any_layer_or_ranking(layer, source_change):
    record, sources = fixture(
        1, layer=layer, category="constraint" if layer == "profile" else "background"
    )
    change = {
        "active": False,
        "redacted": True,
        "incognito": True,
        "revision": 2,
        "owner_id": "other",
        "subject_id": "other",
    }
    name = {"owner": "owner_id", "subject": "subject_id"}.get(
        source_change, source_change
    )
    sources = (
        ()
        if name == "missing"
        else (replace(sources[0], **{name: change[name]}), *sources[1:])
    )
    result = project([(record, sources)])
    assert not any(
        (
            result.constraints,
            result.profile,
            result.open_topics,
            result.rounds,
            result.current_summary,
            result.recent_elsewhere,
            result.retrieval,
        )
    )


@pytest.mark.parametrize(
    "mutation", ["future", "invalid", "deleted", "owner", "subject", "thread"]
)
def test_foreign_invalid_or_future_records_never_enter_context(mutation):
    record, sources = fixture(1)
    changes = {
        "future": {"said_at": AT + timedelta(seconds=1)},
        "invalid": {"valid": False},
        "deleted": {"deleted": True},
        "owner": {"owner_id": "other"},
        "subject": {"subject_id": "other"},
    }
    record = (
        replace(record, life_thread_id="other")
        if mutation == "thread"
        else replace(record, unit=replace(record.unit, **changes[mutation]))
    )
    result = project([(record, sources)])
    assert result.retrieval == ()
    if mutation in {"owner", "subject", "thread"}:
        assert result.omitted_ids == ()


def test_summary_revocation_plans_metadata_invalidation_without_mutating_original():
    record, sources = fixture(1, layer="summary", topic=None)
    revoked = (replace(sources[0], redacted=True),)
    plan = plan_summary_invalidations(
        (record,), revoked, scope=SCOPE, source_epoch=7, clock=FrozenClock(AT)
    )
    assert [(item.id, item.expected_revision) for item in plan.changes] == [
        ("unit-1", 1)
    ]
    assert record.unit.text.startswith("合成私有正文") and record.revision == 1
    assert plan == plan_summary_invalidations(
        (record,), revoked, scope=SCOPE, source_epoch=7, clock=FrozenClock(AT)
    )
    clean = plan_summary_invalidations(
        (record,), sources, scope=SCOPE, source_epoch=7, clock=FrozenClock(AT)
    )
    assert clean.changes == () and clean.operation_id != plan.operation_id


def test_assistant_inference_cannot_be_profile_or_promoted_as_global_constraint():
    record, sources = fixture(1)
    inferred = replace(
        record.unit, kind="note", origin="assistant_claim", inferred=True
    )
    source = replace(sources[0], role="assistant", origin="assistant_claim")
    with pytest.raises(ValueError, match="profile_requires_user_fact"):
        replace(record, unit=inferred, layer="profile")
    result = project([(replace(record, unit=inferred), (source,))])
    assert result.retrieval[0].attribution == "助手推断，非用户事实"
    constrained = replace(inferred, category="constraint")
    assert project([(replace(record, unit=constrained), (source,))]).constraints == ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("score", True),
        ("score", float("inf")),
        ("score", float("nan")),
        ("score", 1.7e308),
        ("score", -1),
        ("revision", True),
        ("revision", 0),
        ("life_thread_id", ""),
        ("space_id", ""),
        ("topic_id", ""),
    ],
)
def test_malformed_record_is_rejected(field, value):
    record, _ = fixture(1)
    with pytest.raises(ValueError):
        replace(record, **{field: value})


def test_duplicate_sources_fail_closed_duplicate_units_raise_and_no_private_repr():
    record, sources = fixture(1)
    assert project([(record, (*sources, sources[0]))]).retrieval == ()
    with pytest.raises(ValueError, match="duplicate_unit"):
        project([(record, sources), (record, sources)])
    result = project([(record, sources)])
    assert "合成私有正文" not in repr(record) + repr(result) + repr(result.retrieval[0])


@pytest.mark.parametrize(
    "zone", ["Asia/Shanghai", "Asia/Tokyo", "UTC", "America/New_York", "Europe/London"]
)
def test_host_timezone_does_not_change_projection_and_epoch_changes_key(zone):
    values = [fixture(1, layer="summary", space="health", days=6), fixture(2)]
    result = project(values, clock=FrozenClock(AT.astimezone(ZoneInfo(zone))))
    assert result == project(values)
    assert result.projection_key != project(values, epoch=1).projection_key


def test_seeded_source_revocation_and_permutation_property_1000_groups():
    generator = random.Random(20261021)
    for group in range(1000):
        values = [
            fixture(
                group * 10 + index,
                space=generator.choice(("career", "health", "family")),
                score=generator.random(),
            )
            for index in range(8)
        ]
        selected = generator.randrange(8)
        record, sources = values[selected]
        values[selected] = record, (replace(sources[0], redacted=True),)
        result = project(values)
        assert len(result.retrieval) == 7 and record.unit.id not in {
            item.id for item in result.retrieval
        }
        generator.shuffle(values)
        assert project(values) == result


def test_huge_integer_score_is_public_value_error_without_private_value():
    record, _ = fixture(1)
    with pytest.raises(ValueError, match="partition_score_invalid"):
        replace(record, score=10**10000)


@pytest.mark.parametrize("epoch", [True, -1, 1.5, "1"])
def test_projection_and_invalidation_reject_malformed_epoch(epoch):
    record, sources = fixture(1, layer="summary", topic=None)
    for function in (project_partition_context, plan_summary_invalidations):
        with pytest.raises(ValueError, match="scope_or_epoch_invalid"):
            function(
                (record,),
                sources,
                scope=SCOPE,
                source_epoch=epoch,
                clock=FrozenClock(AT),
            )


@pytest.mark.parametrize("role", ["assistant", "tool", "legacy"])
def test_facts_cannot_borrow_nonuser_source_for_global_constraints(role):
    record, sources = fixture(1, category="constraint")
    result = project([(record, (replace(sources[0], role=role),))])
    assert result.constraints == ()


def test_foreign_summary_is_not_named_in_invalidation_plan():
    record, sources = fixture(1, layer="summary", topic=None)
    foreign = replace(record, unit=replace(record.unit, owner_id="other-owner"))
    plan = plan_summary_invalidations(
        (foreign,), (), scope=SCOPE, source_epoch=0, clock=FrozenClock(AT)
    )
    assert plan.changes == ()
    assert sources[0].owner_id == SCOPE.owner_id


def test_summary_cannot_pose_as_user_fact_and_other_topic_requires_title():
    summary, _ = fixture(1, layer="summary")
    with pytest.raises(ValueError, match="summary_must_be_marked_derived"):
        replace(summary, unit=replace(summary.unit, inferred=False))
    topic, _ = fixture(2, layer="open_topic")
    with pytest.raises(ValueError, match="open_topic_requires_title"):
        replace(topic, title="")


def test_extractive_english_summary_stops_at_sentence_and_keeps_decimal_amount():
    record, sources = fixture(1, layer="profile", space="finance")
    record = replace(
        record,
        unit=replace(
            record.unit, text="Synthetic budget is 1234.50. Second private detail."
        ),
    )
    result = project([(record, sources)])
    assert result.profile[0].text == "Synthetic budget is 1234.50."

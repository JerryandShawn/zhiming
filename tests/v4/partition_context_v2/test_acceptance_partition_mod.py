"""Independent frozen partition semantics; projections do not authorize persistence or token use."""

import copy
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.memory.retrieval_types import SearchSource, SearchUnit, SourceRef
from mingjing_core.organize.partition_context_v2 import plan_summary_invalidations, project_partition_context
from mingjing_core.organize.partition_context_v2_contracts import PartitionRecord, PartitionScope
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = PartitionScope("owner", "self", "life:self", "career", "interview")
GROUPS = ("constraints", "profile", "open_topics", "rounds", "current_summary", "recent_elsewhere", "retrieval")


def sample(
    identity,
    *,
    layer="retrieval",
    space="career",
    topic="interview",
    at=AT,
    body="SYNTHETIC_PRIVATE_BODY",
    category="background",
    score=1.0,
    title="合成标题",
):
    sources = (SearchSource("u-" + str(identity), SCOPE.owner_id, SCOPE.subject_id),)
    if layer == "round":
        sources += (replace(sources[0], id="a-" + str(identity), role="assistant", origin="system"),)
    kind = {"profile": "fact", "summary": "summary", "open_topic": "topic", "round": "round"}.get(layer, "fact")
    unit = SearchUnit(
        str(identity),
        SCOPE.owner_id,
        SCOPE.subject_id,
        kind,
        body,
        at,
        source_refs=tuple(SourceRef(source.id) for source in sources),
        category=category,
        origin="derived_summary" if layer == "summary" else "user",
        inferred=layer == "summary",
    )
    return PartitionRecord(unit, SCOPE.life_thread_id, space, layer, topic, score, title), sources


def project(values, *, source_epoch=1, clock=None, scope=SCOPE, sources=None):
    return project_partition_context(
        tuple(record for record, _ in values),
        tuple(source for _, state in values for source in state) if sources is None else sources,
        scope=scope,
        source_epoch=source_epoch,
        clock=clock or FrozenClock(AT),
    )


def lines(result):
    return tuple(row for group in GROUPS for row in getattr(result, group))


@pytest.mark.parametrize(
    "guard",
    [
        "wrong_owner",
        "wrong_subject",
        "missing",
        "stale",
        "inactive",
        "redacted",
        "incognito",
        "assistant_role",
        "legacy_origin",
        "duplicate_source",
    ],
)
def test_current_original_source_guards_filter_private_text_and_all_citations(guard):
    record, sources = sample("guarded")
    if guard in {"wrong_owner", "wrong_subject"}:
        record = replace(
            record, unit=replace(record.unit, **{"owner_id" if guard == "wrong_owner" else "subject_id": "other"})
        )
    elif guard == "missing":
        sources = ()
    elif guard == "duplicate_source":
        sources = sources + sources
    else:
        change = {
            "stale": {"revision": 2},
            "inactive": {"active": False},
            "redacted": {"redacted": True},
            "incognito": {"incognito": True},
            "assistant_role": {"role": "assistant", "origin": "system"},
            "legacy_origin": {"origin": "legacy_import"},
        }[guard]
        sources = (replace(sources[0], **change),)
    result = project([(record, sources)])
    assert not lines(result)
    assert "SYNTHETIC_PRIVATE_BODY" not in repr(asdict(result))


@pytest.mark.parametrize("guard", ["one_ref", "reversed_roles", "missing_assistant", "revoked_assistant"])
def test_a_round_requires_the_complete_current_user_then_assistant_pair(guard):
    record, sources = sample("pair", layer="round", body="USER_FULL\nASSISTANT_FULL")
    if guard == "one_ref":
        record = replace(record, unit=replace(record.unit, source_refs=record.unit.source_refs[:1]))
    elif guard == "reversed_roles":
        record = replace(record, unit=replace(record.unit, source_refs=tuple(reversed(record.unit.source_refs))))
    elif guard == "missing_assistant":
        sources = sources[:1]
    else:
        sources = (sources[0], replace(sources[1], active=False))
    result = project([(record, sources)])
    assert not result.rounds and "USER_FULL" not in repr(asdict(result))


def test_latest_thirty_whole_rounds_are_from_only_the_same_life_area_and_topic():
    values = [
        sample(
            f"round-{index}",
            layer="round",
            at=AT - timedelta(minutes=40 - index),
            body=f"USER_{index}_COMPLETE\nASSISTANT_{index}_COMPLETE",
        )
        for index in range(35)
    ]
    for index, change in enumerate(
        [{"space_id": "family"}, {"topic_id": "another"}, {"life_thread_id": "another-life"}]
    ):
        record, sources = sample(f"foreign-{index}", layer="round", at=AT)
        values.append((replace(record, **change), sources))
    future = sample("future", layer="round", at=AT + timedelta(microseconds=1))
    result = project([*values, future])
    assert [row.id for row in result.rounds] == [f"round-{index}" for index in range(5, 35)]
    for index, row in enumerate(result.rounds, 5):
        assert row.text == f"USER_{index}_COMPLETE\nASSISTANT_{index}_COMPLETE"
        assert len(row.source_refs) == 2 and not row.abbreviated


def test_genuine_constraints_remain_global_and_current_area_score_is_exactly_one_point_five():
    constraint = sample("constraint", category="constraint", space="family", score=0)
    current = sample("current", score=1)
    other = sample("other", space="family", score=1.4)
    result = project([constraint, current, other])
    assert [row.id for row in result.constraints] == ["constraint"]
    assert [(row.id, row.weighted_score) for row in result.retrieval] == [("current", 1.5), ("other", 1.4)]


@pytest.mark.parametrize("origin", ["assistant_claim", "derived_summary", "inferred_user"])
def test_assistant_and_derived_material_cannot_impersonate_a_global_user_constraint(origin):
    record, sources = sample(
        "fake", layer="summary" if origin == "derived_summary" else "retrieval", category="constraint"
    )
    if origin == "assistant_claim":
        sources = (replace(sources[0], role="assistant", origin="system"),)
        record = replace(record, unit=replace(record.unit, kind="note", origin="assistant_claim"))
    elif origin == "inferred_user":
        record = replace(record, unit=replace(record.unit, inferred=True))
    result = project([(record, sources)])
    assert not result.constraints and not lines(result)


@pytest.mark.parametrize(
    ("other_text", "expected"),
    [
        ("第一句。第二个私有细节。", "第一句"),
        ("first fact. second private detail.", "first fact."),
        ("balance 1234.50 units. second private detail.", "balance 1234.50 units."),
    ],
)
def test_current_profile_keeps_detail_while_other_profile_is_only_one_sentence(other_text, expected):
    current = sample("z-current", layer="profile", body="当前第一句。当前第二句。")
    other = sample("a-other", layer="profile", space="family", body=other_text)
    result = project([other, current])
    assert [row.id for row in result.profile] == ["z-current", "a-other"]
    assert result.profile[0].text == current[0].unit.text and not result.profile[0].abbreviated
    assert result.profile[1].text == expected and result.profile[1].abbreviated


def test_open_topics_from_other_areas_expose_titles_without_their_full_private_body():
    current = sample("current-topic", layer="open_topic", body="完整当前事项细节", title="当前标题")
    other = sample(
        "other-topic", layer="open_topic", space="family", body="SYNTHETIC_OTHER_TOPIC_BODY", title="家庭标题"
    )
    result = project([other, current])
    assert [row.text for row in result.open_topics] == ["完整当前事项细节", "家庭标题"]
    assert "SYNTHETIC_OTHER_TOPIC_BODY" not in repr(asdict(result))


@pytest.mark.parametrize(
    ("offset", "included"),
    [(timedelta(days=7), True), (timedelta(days=7, microseconds=1), False), (-timedelta(microseconds=1), False)],
)
def test_other_area_summary_uses_inclusive_utc_seven_day_boundary_and_excludes_future(offset, included):
    value = sample("boundary", layer="summary", space="family", at=AT - offset)
    result = project([value])
    assert bool(result.recent_elsewhere) == included
    assert not result.profile and not result.constraints


def test_latest_two_summaries_per_other_area_are_displayed_in_chronological_order_and_marked_derived():
    values = [
        sample(f"{space}-{age}", layer="summary", space=space, at=AT - timedelta(hours=age))
        for space in ("family", "wellbeing")
        for age in (1, 2, 3)
    ]
    result = project(values)
    for space in ("family", "wellbeing"):
        selected = [row for row in result.recent_elsewhere if row.space_id == space]
        assert [row.id for row in selected] == [f"{space}-2", f"{space}-1"]
        assert all("派生" in row.attribution and "非新增用户事实" in row.attribution for row in selected)
    assert not result.profile and not result.constraints


def test_current_summary_is_latest_area_summary_and_withdrawal_produces_only_revision_bound_intent():
    old = sample("old", layer="summary", topic=None, at=AT - timedelta(hours=2))
    current = sample("latest", layer="summary", topic=None, at=AT - timedelta(hours=1))
    record, sources = sample("withdrawn", layer="summary", space="family")
    record, sources = replace(record, revision=7), (replace(sources[0], redacted=True),)
    foreign, foreign_sources = sample("foreign", layer="summary", space="family")
    foreign = replace(foreign, unit=replace(foreign.unit, owner_id="other"))
    values = [old, current, (record, sources), (foreign, foreign_sources)]
    before = copy.deepcopy(values)
    result = project(values)
    assert [row.id for row in result.current_summary] == ["latest"]
    assert not result.recent_elsewhere
    records, states = tuple(value[0] for value in values), tuple(source for _, states in values for source in states)
    plan = plan_summary_invalidations(records, states, scope=SCOPE, source_epoch=9, clock=FrozenClock(AT))
    replay = plan_summary_invalidations(records, states, scope=SCOPE, source_epoch=9, clock=FrozenClock(AT))
    assert plan == replay and plan.source_epoch == 9 and plan.operation_id
    assert [(change.id, change.expected_revision) for change in plan.changes] == [("withdrawn", 7)]
    assert values == before and record.unit.valid and not record.unit.deleted


def test_derived_summary_cannot_be_placed_into_a_user_profile_layer():
    record, _ = sample("summary", layer="summary")
    with pytest.raises(ValueError):
        replace(record, layer="profile")


def test_open_topic_requires_an_explicit_nonempty_title():
    record, _ = sample("topic", layer="open_topic")
    with pytest.raises(ValueError):
        replace(record, title="")


def test_absent_current_topic_does_not_invent_a_current_round():
    result = project([sample("pair", layer="round")], scope=replace(SCOPE, topic_id=None))
    assert not result.rounds


def test_naive_clock_never_borrows_the_host_timezone():
    class NaiveClock:
        def now(self):
            return datetime(2026, 10, 21)

    with pytest.raises(ValueError):
        project([sample("fact")], clock=NaiveClock())


@pytest.mark.parametrize("zone", ["UTC", "Asia/Tokyo", "America/New_York", "Europe/Berlin", "Australia/Sydney"])
def test_projection_is_time_representation_independent_and_epoch_is_part_of_consistency_key(zone):
    values = [sample("current"), sample("family", layer="summary", space="family", at=AT - timedelta(days=2))]
    original = copy.deepcopy(values)
    result = project(values)
    mirrored = project(values, clock=FrozenClock(AT.astimezone(ZoneInfo(zone))))
    changed = project(values, source_epoch=2)
    assert result == mirrored and result.projection_key != changed.projection_key
    assert result.retrieval == changed.retrieval and values == original

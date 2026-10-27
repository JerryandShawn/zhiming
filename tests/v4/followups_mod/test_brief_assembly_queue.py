from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from mingjing_core.application.brief_assembly import (
    BriefMaterial,
    BriefSource,
    assemble_brief,
)
from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.timekit.clock import FrozenClock

SCOPE = FollowupScope("synthetic-owner", "synthetic-subject")


def at(value="2026-10-10T07:00:00+08:00"):
    return datetime.fromisoformat(value)


def material(kind="agenda", **changes):
    return replace(
        BriefMaterial(
            "synthetic-source",
            SCOPE,
            1,
            "m1",
            kind,
            "合成事项核对计划",
            at() + timedelta(hours=2),
        ),
        **changes,
    )


def source(row):
    return BriefSource(row.source_id, SCOPE, row.revision, row.digest)


def assemble(rows=(), states=(), **kwargs):
    send = kwargs.pop("send_at", at())
    return assemble_brief(
        rows,
        states,
        scope=SCOPE,
        send_at=send,
        clock=FrozenClock(send - timedelta(minutes=15)),
        **kwargs,
    )


def test_calendar_is_anchored_to_send_time_not_preparation_and_marks_adjusted_workday():
    row = material()
    result = assemble([row], [source(row)])
    assert "2026-10-10" in result.now_block
    assert "调休上班日" in result.now_block
    assert "07:00" in result.now_block
    assert "合成事项核对计划〔m1〕" in result.now_block
    assert result.preview == "明镜的晨报到了"
    assert "合成事项" not in repr(result)


def test_weekend_and_chongyang_context_are_reused_from_timekit():
    result = assemble(send_at=at("2026-10-17T07:00:00+08:00"))
    assert "周六" in result.now_block
    assert "重阳" in result.now_block and "明天" in result.now_block


@pytest.mark.parametrize(
    "change",
    [
        {"revoked": True},
        {"active": False},
        {"incognito": True},
        {"revision": 2},
        {"digest": "0" * 64},
    ],
)
def test_invalid_current_sources_are_not_exposed(change):
    row = material()
    result = assemble([row], [replace(source(row), **change)])
    assert result.materials == () and result.omissions
    assert row.text not in result.now_block


def test_transit_requires_current_confirmed_profile_and_exact_local_day():
    row = material("transit", alias="c1", profile_revision=2)
    assert not assemble([row], [source(row)]).materials
    assert assemble([row], [source(row)], confirmed_profile_revision=2).materials == (
        row,
    )
    assert not assemble([row], [source(row)], confirmed_profile_revision=3).materials
    tomorrow = replace(row, at=row.at + timedelta(days=1))
    assert not assemble(
        [tomorrow], [source(tomorrow)], confirmed_profile_revision=2
    ).materials


def test_no_unconfirmed_transit_is_invented_and_dependency_copy_is_omitted():
    assert assemble().materials == ()
    row = material(text="记得每天来看")
    result = assemble([row], [source(row)])
    assert result.omissions == (("m1", "dependency_copy"),)


def test_scope_alias_collisions_and_stale_preparation_fail_closed():
    row = material()
    with pytest.raises(ValueError, match="scope"):
        assemble(
            [replace(row, scope=FollowupScope("foreign", "subject"))], [source(row)]
        )
    with pytest.raises(ValueError, match="collision"):
        assemble([row, row], [source(row)])
    with pytest.raises(ValueError, match="fifteen"):
        assemble_brief(
            [],
            [],
            scope=SCOPE,
            send_at=at(),
            clock=FrozenClock(at() - timedelta(minutes=16)),
        )


@pytest.mark.parametrize(
    "kind,start,end",
    [
        ("weekly", "2026-10-05", "2026-10-11"),
        ("monthly", "2026-10-01", "2026-10-31"),
        ("quarterly", "2026-10-01", "2026-12-31"),
    ],
)
def test_report_bounds_are_real_periods_not_invented_rolling_ranges(kind, start, end):
    result = assemble(report_kind=kind)
    assert result.period_start.isoformat() == start
    assert result.period_end.isoformat() == end


def test_episode_summary_stays_in_the_actual_report_period():
    row = material("episode", at=at() - timedelta(days=10))
    assert not assemble([row], [source(row)], report_kind="weekly").materials
    current = replace(row, at=at())
    assert assemble([current], [source(current)], report_kind="weekly").materials == (
        current,
    )

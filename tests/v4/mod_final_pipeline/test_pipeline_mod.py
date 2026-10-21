"""Frozen independent source-lifecycle truths compose real public modules, never live services."""

import hashlib
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from random import Random
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.reflection_v3 import (
    BackgroundPermit,
    ReflectionOperation,
    plan_reflection_work,
    render_about_me,
    schedule_reflection,
)
from mingjing_core.application.reports_v2 import period_for
from mingjing_core.memory2.guards import MemoryGuardError, authorize_fact
from mingjing_core.memory2.mutations import apply_plan

from .support_mod import (
    FIXTURE,
    MATRIX,
    SCOPE,
    current_records,
    pipeline,
    profile,
    records,
    report,
    schedule,
    scheduling,
)

AT = datetime(2026, 10, 21, 5, tzinfo=UTC)


def render(value: object, snapshot: object, document: object) -> object:
    return render_about_me(
        document, snapshot=snapshot, scope=SCOPE, clock=value.clock, current_profile_revision=document.revision
    )


def private_text(result: object) -> str:
    return "\n".join(line.text for section in result.sections for line in section.lines)


def check_positive(value: object, kind: str) -> tuple:
    snapshot, document = value.snapshot, profile(value)
    assert value.saved is not None and value.saved.write_status == "saved" and len(snapshot.facts) == 1
    decision = schedule(value)
    assert decision.intent is not None
    work = plan_reflection_work(
        decision.intent,
        snapshot=snapshot,
        thread=value.thread,
        scope=SCOPE,
        clock=value.clock,
        permit=value.permit,
        profile=document,
        current_profile_revision=document.revision,
    )
    assert work.status == "planned" and work.rolling_summary is not None
    assert work.rolling_summary.excerpts[0].anchor.quote == value.source.text
    view = render(value, snapshot, document)
    assert len(view.sections) == 8 and private_text(view) == snapshot.facts[0].text
    cached = records(value, view)
    compiled = report(value, cached, kind=kind)
    assert value.source.text in private_text(compiled)
    assert compiled.used_record_ids == (snapshot.facts[0].id,)
    assert any(section.area_id == value.area and section.category == "fact" for section in compiled.sections)
    assert all(number == 0 for result in (work, view, compiled) for number in asdict(result.effects).values())
    return decision, document, cached, compiled


def test_fixture_is_frozen_and_explicitly_synthetic() -> None:
    assert (
        hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        == "90074adfba23e5d2ba0d8f049743ecb52bbf9dad4fcd37587a6565d172dfe5f5"
    )
    assert MATRIX["synthetic_only"] is True and len(MATRIX["cases"]) == 41


@pytest.mark.parametrize(
    "case", [row for row in MATRIX["cases"] if row["family"] == "baseline"], ids=lambda row: row["id"]
)
def test_original_quote_survives_memory_reflection_eight_section_render_and_period_report(case: dict) -> None:
    check_positive(pipeline(MATRIX["texts"][case["area"]], AT, area=case["area"]), case["report_kind"])


@pytest.mark.parametrize(
    "case", [row for row in MATRIX["cases"] if row["family"] == "invalidate"], ids=lambda row: row["id"]
)
def test_current_source_change_invalidates_old_work_pin_edited_profile_and_cached_report_without_prefilter(
    case: dict,
) -> None:
    value = pipeline(MATRIX["texts"]["daily"], AT)
    decision, _, cached, before = check_positive(value, "weekly")
    document = profile(value, pinned=True, edited=True)
    snapshot, change = value.snapshot, case["change"]
    changes = {
        "revoked": {"revoked": True},
        "inactive": {"active": False},
        "incognito": {"incognito": True},
        "optout_flag": {"optout": True},
        "text_same_revision": {"text": "这是另一条明确虚构的新正文。"},
        "role_assistant": {"role": "assistant", "origin": "system"},
        "origin_external": {"origin": "external"},
    }
    current = (
        replace(snapshot, source_epoch=snapshot.source_epoch + 1)
        if change == "epoch_only"
        else replace(snapshot, sources=(replace(value.source, **changes[change]),))
    )
    work = plan_reflection_work(
        decision.intent,
        snapshot=current,
        thread=value.thread,
        scope=SCOPE,
        clock=value.clock,
        permit=value.permit,
        profile=document,
        current_profile_revision=document.revision,
    )
    assert work.status == "blocked" and not work.episodes and not work.profile_proposals
    view = render(value, current, document)
    compiled = report(value, current_records(cached, current))
    assert not any(section.lines for section in view.sections)
    assert value.source.text not in view.markdown and value.source.text not in private_text(compiled)
    assert not compiled.used_record_ids and compiled.request_key != before.request_key
    if change != "epoch_only":
        assert current.source_epoch == snapshot.source_epoch and current.revision == snapshot.revision
        with pytest.raises(MemoryGuardError):
            authorize_fact(snapshot.facts[0], current, SCOPE)
    assert all(number == 0 for result in (work, view, compiled) for number in asdict(result.effects).values())


@pytest.mark.parametrize(
    "case", [row for row in MATRIX["cases"] if row["family"] == "policy"], ids=lambda row: row["id"]
)
def test_non_user_sensitive_optout_and_secret_candidates_do_not_create_user_profile_or_report(case: dict) -> None:
    value = pipeline(MATRIX["texts"][case["text_key"]], AT, assistant=case["text_key"] == "assistant")
    assert value.plan.policy_action == "reject" if value.saved is None else value.saved.write_status != "saved"
    assert not value.snapshot.facts
    document = profile(value)
    view = render(value, value.snapshot, document)
    compiled = report(value, records(value, view))
    assert not any(section.lines for section in view.sections) and not compiled.used_record_ids
    assert value.source.text not in private_text(compiled)


def test_same_memory_operation_and_same_reflection_operation_do_not_duplicate_the_report() -> None:
    value = pipeline(MATRIX["texts"]["career"], AT, area="career")
    decision, _, cached, original = check_positive(value, "weekly")
    replay = apply_plan(value.snapshot, value.plan, clock=value.clock)
    assert replay.replayed and replay.snapshot == value.snapshot and len(replay.snapshot.facts) == 1
    ledger = (
        ReflectionOperation(SCOPE, value.thread.id, decision.intent.operation_id, decision.intent.input_fingerprint),
    )
    again = schedule_reflection(**scheduling(value), operations=ledger)
    assert again.replayed and again.intent is None
    compiled = report(value, cached)
    assert compiled.used_record_ids == original.used_record_ids and compiled.request_key == original.request_key


@pytest.mark.parametrize(
    "case", [row for row in MATRIX["cases"] if row["family"] == "halfopen"], ids=lambda row: row["id"]
)
@pytest.mark.parametrize("zone", MATRIX["zones"])
def test_source_to_profile_to_report_obeys_the_real_half_open_period(case: dict, zone: str) -> None:
    target = date(2026, 10, 21)
    period = period_for("weekly", target, zone)
    left = datetime(2026, 10, 19, tzinfo=ZoneInfo(zone)).astimezone(UTC)
    right = datetime(2026, 10, 26, tzinfo=ZoneInfo(zone)).astimezone(UTC)
    assert (period.start, period.end) == (left, right)
    instants = {
        "at_start": period.start,
        "before_start": period.start - timedelta(microseconds=1),
        "at_end": period.end,
        "before_end": period.end - timedelta(microseconds=1),
    }
    value = pipeline(
        MATRIX["texts"]["daily"], period.end + timedelta(hours=1), said_at=instants[case["boundary"]], timezone=zone
    )
    view = render(value, value.snapshot, profile(value))
    assert private_text(view) == value.source.text
    compiled = report(value, records(value, view), day=target)
    assert bool(compiled.used_record_ids) is case["expected_visible"]
    assert (value.source.text in private_text(compiled)) is case["expected_visible"]


def test_default_background_permission_is_closed_and_every_composed_effect_is_zero() -> None:
    value = pipeline(MATRIX["texts"]["daily"], AT)
    decision = schedule_reflection(**{**scheduling(value), "permit": BackgroundPermit(SCOPE, 1, 1)})
    assert decision.disposition == "blocked" and decision.intent is None
    check_positive(value, "weekly")


@pytest.mark.parametrize(
    "case", [row for row in MATRIX["cases"] if row["family"] == "protected"], ids=lambda row: row["id"]
)
def test_pin_or_user_edit_cannot_revive_a_revoked_source_in_any_output(case: dict) -> None:
    value = pipeline(MATRIX["texts"]["daily"], AT)
    flag = case["flag"]
    document = profile(value, pinned=flag in {"pinned", "both"}, edited=flag in {"edited_by_user", "both"})
    before = render(value, value.snapshot, document)
    assert private_text(before) == value.source.text
    cached = records(value, before)
    current = replace(value.snapshot, sources=(replace(value.source, revoked=True),))
    after = render(value, current, document)
    compiled = report(value, current_records(cached, current))
    assert not private_text(after) and value.source.text not in private_text(compiled)
    assert not compiled.used_record_ids and after.omitted_item_ids == (document.entries[0].item.id,)


def test_one_thousand_seeded_complete_chains_across_six_owner_zones_and_day_boundaries() -> None:
    rng = Random(MATRIX["random_seed"])
    areas = ["daily", "career", "relationships", "family", "wellbeing", "finance", "metaphysics"]
    for index in range(MATRIX["random_trials"]):
        at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=rng.randrange(365), seconds=rng.randrange(86400))
        area, zone = areas[index % 7], MATRIX["zones"][index % 6]
        if at.astimezone(ZoneInfo(zone)).hour == 0 and at.astimezone(ZoneInfo(zone)).minute < 20:
            at += timedelta(minutes=20)
        value = pipeline(MATRIX["texts"][area], at, area=area, timezone=zone, said_at=at - timedelta(minutes=10))
        kind = ("weekly", "monthly", "quarterly")[index % 3]
        decision, document, cached, before = check_positive(value, kind)
        changed = replace(value.snapshot, sources=(replace(value.source, revoked=True),))
        after_work = plan_reflection_work(
            decision.intent,
            snapshot=changed,
            thread=value.thread,
            scope=SCOPE,
            clock=value.clock,
            permit=value.permit,
            profile=document,
            current_profile_revision=document.revision,
        )
        after_view = render(value, changed, document)
        after_report = report(value, current_records(cached, changed), kind=kind)
        assert after_work.status == "blocked" and not after_work.rolling_summary
        assert not private_text(after_view) and value.source.text not in private_text(after_report)
        assert not after_report.used_record_ids and after_report.request_key != before.request_key

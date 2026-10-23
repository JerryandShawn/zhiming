"""Independent frozen-clock, explicit-zone and zero-effect briefing properties."""

import copy
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, time, timedelta
from random import Random
from zoneinfo import ZoneInfo

import pytest
from brief_acceptance_support_mod import BASE, SCOPE, compose, context, item, public_text

from mingjing_core.timekit.clock import FrozenClock

ZONES = ("Asia/Shanghai", "Asia/Tokyo", "UTC", "America/New_York", "Europe/Berlin", "Australia/Sydney")


@pytest.mark.parametrize("seed", range(40))
def test_1000_random_owner_dates_zones_and_clock_representations_are_deterministic_and_effect_free(seed):
    rng = Random(210946 + seed)
    for _ in range(25):
        zone = ZoneInfo(rng.choice(ZONES))
        day = date(2026, 1, 1) + timedelta(days=rng.randrange(365 * 2))
        at = datetime.combine(day, time(rng.choice([0, 7, 12, 23]), rng.choice([0, 1, 59])), zone)
        values = context(at=at, zone=zone.key)
        entry = item(due=datetime.combine(day, time(9), zone))
        result = compose(values, items=(entry,))
        mirrored = compose(values, items=(entry,), clock=FrozenClock(at.astimezone(UTC)))
        assert result == mirrored and result.day == day and result.timezone == zone.key
        assert result.generated_at == at and result.scope == SCOPE
        assert all(value == 0 for value in asdict(result.effects).values())
        assert values["clock"].now() == at and values["calendar"].day == day
        assert entry.request.original_due == datetime.combine(day, time(9), zone)


def test_same_inputs_replay_without_mutating_transit_private_sources_or_scheduling_state():
    values = context(include_transit=True)
    entry = item(body="SYNTHETIC_CONFIRMED_SUMMARY")
    original = copy.deepcopy(values["transit"])
    first = compose(values, items=(entry,))
    second = compose(values, items=(entry,))
    assert first == second and first.request_key == second.request_key
    assert values["transit"] == original and entry.request.candidate.text == "SYNTHETIC_CONFIRMED_SUMMARY"
    assert all(value == 0 for value in asdict(first.effects).values())
    assert not any(phrase in public_text(first) for phrase in ("已发送提醒", "已保存这条", "全局依据已登记"))


def test_owner_zone_date_does_not_silently_reuse_a_different_beijing_transit_day():
    values = context(at=BASE, zone="America/New_York", include_transit=True)
    result = compose(values)
    assert result.day == date(2026, 10, 20)
    assert not any(ref.document_id == values["transit"]["document_id"] for ref in result.basis)
    assert result.warnings


@pytest.mark.parametrize("age", [timedelta(minutes=15, microseconds=1), -timedelta(microseconds=1)])
def test_calendar_snapshot_cannot_be_stale_or_observed_in_the_future(age):
    values = context()
    changed = replace(values["calendar"], observed_at=BASE - age)
    with pytest.raises(ValueError):
        compose(values, calendar=changed)


def test_exact_fifteen_minute_preparation_snapshot_remains_eligible_at_delivery():
    values = context(at=BASE - timedelta(minutes=15))
    result = compose(values, clock=FrozenClock(BASE))
    assert result.generated_at == BASE and result.delivery.allowed
    assert result.sections and result.effects.notifications == 0


def test_unpublished_holiday_arrangements_are_labeled_instead_of_asserting_known_leave():
    values = context(at=datetime(2027, 1, 4, 7, tzinfo=ZoneInfo("Asia/Shanghai")))
    assert values["calendar"].day_status.source == "unpublished"
    result = compose(values)
    assert any(word in public_text(result) for word in ("未公布", "尚未发布", "未发布"))


def test_naive_clock_never_implicitly_uses_the_hosts_tokyo_timezone():
    class NaiveClock:
        def now(self):
            return datetime(2026, 10, 21, 7)

    with pytest.raises(ValueError):
        compose(context(), clock=NaiveClock())


def test_subscription_revision_change_alters_occurrence_binding_without_creating_a_send_receipt():
    from brief_acceptance_support_mod import source_state

    from mingjing_core.application.briefing_v2 import subscription_basis

    values = context()
    first = compose(values)
    changed = replace(values["subscription"], revision=2)
    second = compose(values, subscription=changed, subscription_state=source_state(subscription_basis(changed)))
    assert first.request_key != second.request_key
    assert first.effects.notifications == second.effects.notifications == 0

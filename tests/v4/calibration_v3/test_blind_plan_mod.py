"""Independent blinding and daily opening plans without real labels or reviewer actions."""

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timekit.clock import FrozenClock
from tools.calibration_v3 import private_export
from tools.calibration_v3.batches import ReviewScope, blind_payload, make_blind_plan
from tools.calibration_v3.daily import OpeningLedger, plan_open_batch
from tools.calibration_v3.models import ITEMS, CalibrationError

from .calibration_toy_support_mod import TOY_BODY, toy_plan

AT = datetime(2026, 10, 21, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_five_fifteen_batches_cover_all_samples_with_priority_and_no_adjacent_item() -> None:
    dataset, plan = toy_plan()
    assert [len(batch.refs) for batch in plan.batches] == [15] * 5
    refs = [ref for batch in plan.batches for ref in batch.refs]
    assert {ref.sample_id for ref in refs} == {sample.source_id for sample in dataset.samples}
    assert len({ref.blind_id for ref in refs}) == 75
    assert all(left.item != right.item for left, right in zip(refs, refs[1:], strict=False))
    assert {sample.source_id for sample in dataset.samples if sample.uncertain} <= {
        ref.sample_id for ref in plan.batches[0].refs
    }
    assert all({ref.item for ref in batch.refs} == set(ITEMS) for batch in plan.batches)


def test_blind_user_payload_contains_no_gold_reason_class_title_or_original_case_id() -> None:
    dataset, plan = toy_plan()
    payload = blind_payload(dataset, plan, plan.batches[0])
    assert all(set(candidate) == {"id", "material", "user", "draft"} for candidate in payload["candidates"])
    raw = json.dumps(payload)
    assert "toy-rationale" not in raw and '"labels"' not in raw and '"uncertain"' not in raw
    assert all(sample.source_id not in raw for sample in dataset.samples)
    assert payload["candidates"][0]["draft"] == TOY_BODY


def test_same_seed_scope_data_and_rubric_are_reproducible_but_foreign_owner_is_not_reused() -> None:
    dataset, plan = toy_plan()
    again = make_blind_plan(dataset, scope=plan.scope, rubric_sha256=plan.rubric_sha256, seed=plan.seed)
    assert plan == again and plan.sha256 == again.sha256
    foreign = make_blind_plan(dataset, scope=ReviewScope("other", "toy-reviewer"), rubric_sha256=plan.rubric_sha256)
    assert plan.sha256 != foreign.sha256
    assert not (
        {ref.blind_id for batch in plan.batches for ref in batch.refs}
        & {ref.blind_id for batch in foreign.batches for ref in batch.refs}
    )


def test_opening_is_an_intent_replay_is_idempotent_and_second_same_day_is_deferred() -> None:
    _, plan = toy_plan()
    ledger, clock = OpeningLedger(plan.sha256), FrozenClock(AT)
    first = plan_open_batch(plan, ledger, clock=clock, operation_id="first", expected_revision=0)
    assert first.status == "opening_intent" and first.ledger.revision == 1
    replay = plan_open_batch(plan, first.ledger, clock=clock, operation_id="first", expected_revision=0)
    assert replay.status == "replayed" and replay.ledger is first.ledger
    second = plan_open_batch(plan, first.ledger, clock=clock, operation_id="second", expected_revision=1)
    assert second.status == "deferred" and second.batch is None
    assert second.next_allowed_at == datetime(2026, 10, 21, 16, tzinfo=UTC)
    clock.advance(timedelta(hours=17))
    tomorrow = plan_open_batch(plan, first.ledger, clock=clock, operation_id="second", expected_revision=1)
    assert tomorrow.status == "opening_intent" and tomorrow.batch.ordinal == 2


@pytest.mark.parametrize("zone", ["UTC", "Asia/Shanghai", "Asia/Tokyo", "America/New_York", "Europe/Berlin"])
def test_daily_limit_uses_beijing_day_not_host_or_clock_representation(zone: str) -> None:
    _, plan = toy_plan()
    now = AT.astimezone(ZoneInfo(zone))
    first = plan_open_batch(
        plan, OpeningLedger(plan.sha256), clock=FrozenClock(now), operation_id="one", expected_revision=0
    )
    result = plan_open_batch(plan, first.ledger, clock=FrozenClock(now), operation_id="two", expected_revision=1)
    assert result.status == "deferred"


def test_one_thousand_random_clock_requests_never_open_two_batches_on_one_beijing_day() -> None:
    _, plan = toy_plan()
    clock, ledger = FrozenClock(AT), OpeningLedger(plan.sha256)
    rng = Random(2026102104)
    for index in range(1000):
        clock.advance(timedelta(minutes=rng.randrange(61)))
        decision = plan_open_batch(
            plan, ledger, clock=clock, operation_id=f"op-{index}", expected_revision=ledger.revision
        )
        ledger = decision.ledger
        days = [row.opened_at.astimezone(ZoneInfo("Asia/Shanghai")).date() for row in ledger.entries]
        assert len(days) == len(set(days)) and len(days) <= 5
    assert len(ledger.entries) == 5


def test_foreign_plan_revision_regression_and_naive_clock_are_rejected() -> None:
    _, plan = toy_plan()
    clock = FrozenClock(AT)
    with pytest.raises(CalibrationError):
        plan_open_batch(plan, OpeningLedger("e" * 64), clock=clock, operation_id="op", expected_revision=0)
    with pytest.raises(CalibrationError):
        plan_open_batch(plan, OpeningLedger(plan.sha256), clock=clock, operation_id="op", expected_revision=True)
    first = plan_open_batch(plan, OpeningLedger(plan.sha256), clock=clock, operation_id="op", expected_revision=0)
    with pytest.raises(CalibrationError):
        plan_open_batch(
            plan, first.ledger, clock=FrozenClock(AT - timedelta(seconds=1)), operation_id="new", expected_revision=1
        )


def test_private_export_cannot_write_full_text_to_public_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset, plan = toy_plan()
    monkeypatch.setattr(private_export, "REPO", tmp_path)
    monkeypatch.setattr(private_export, "PRIVATE", tmp_path / "private/calibration/v2")
    with pytest.raises(CalibrationError):
        private_export.export_private(dataset, plan, output=tmp_path / "docs/leak")
    output = tmp_path / "private/calibration/v2/new"
    summary = private_export.export_private(dataset, plan, output=output)
    assert TOY_BODY not in json.dumps(summary) and summary["mode"] == "record_only"
    assert summary["human_verified_count"] == 0 and summary["runtime_revision_enabled"] is False
    assert len(list(output.glob("*.json"))) == 8
    frozen = copy.deepcopy(summary)
    with pytest.raises(CalibrationError):
        private_export.export_private(dataset, plan, output=output)
    assert summary == frozen


def test_unknown_or_reused_plan_sample_is_invalid() -> None:
    _, plan = toy_plan()
    first = plan.batches[0]
    duplicate = replace(first, refs=(*first.refs[:-1], first.refs[0]))
    with pytest.raises(CalibrationError):
        replace(plan, batches=(duplicate, *plan.batches[1:]))


def test_naive_host_clock_cannot_open_a_review_batch() -> None:
    class NaiveClock:
        def now(self) -> datetime:
            return datetime(2026, 10, 21, 7)

    _, plan = toy_plan()
    with pytest.raises(CalibrationError):
        plan_open_batch(plan, OpeningLedger(plan.sha256), clock=NaiveClock(), operation_id="op", expected_revision=0)

"""Only toy UI inputs; valid unsigned submissions never become verified human labels."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mingjing_core.timekit.clock import FrozenClock
from tools.calibration_v3.batches import blind_payload
from tools.calibration_v3.blind_payload_contract import blind_payload_digest
from tools.calibration_v3.daily import OpeningLedger, plan_open_batch
from tools.calibration_v3.models import ITEMS, CalibrationError
from tools.calibration_v3.submission import validate_submission

from .calibration_toy_support_mod import toy_plan

AT = datetime(2026, 10, 21, 1, tzinfo=UTC)
SCHEMA = json.loads((Path(__file__).parents[3] / "tools/calibration_v3/human_submission.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def submission() -> tuple:
    dataset, plan = toy_plan()
    clock = FrozenClock(AT)
    ledger = plan_open_batch(
        plan, OpeningLedger(plan.sha256), clock=clock, operation_id="toy-ui-open", expected_revision=0
    ).ledger
    value = {
        "schema": "human-review-submission-v3.1",
        "submission_id": "toy-unsigned-submission",
        "owner_id": plan.scope.owner_id,
        "reviewer_id": plan.scope.reviewer_id,
        "plan_sha256": plan.sha256,
        "dataset_sha256": dataset.sha256,
        "rubric_sha256": plan.rubric_sha256,
        "payload_sha256": blind_payload_digest(blind_payload(dataset, plan, plan.batches[0])),
        "batch_id": plan.batches[0].id,
        "submitted_at": AT.isoformat(),
        "answers": [
            {
                "blind_id": ref.blind_id,
                "items": {item: {"violation": False, "severity": None, "uncertain": False} for item in ITEMS},
            }
            for ref in plan.batches[0].refs
        ],
    }
    return value, dataset, plan, ledger, clock


def test_whole_batch_schema_and_semantic_validation_do_not_authenticate_a_human() -> None:
    value, dataset, plan, ledger, clock = submission()
    VALIDATOR.validate(value)
    result = validate_submission(value, dataset=dataset, plan=plan, ledger=ledger, clock=clock)
    assert result.status == "unverified_submission" and result.verified_human_count == 0
    assert result.answer_count == 15 and not result.runtime_revision_enabled
    assert "items" not in repr(result)


@pytest.mark.parametrize(
    "change",
    [
        "missing_item",
        "missing_answer",
        "duplicate_answer",
        "label_hint",
        "truthy_label",
        "truthy_uncertain",
        "false_severity",
        "true_no_severity",
        "severity_bool",
        "extra_top",
        "naive_time",
        "future_time",
    ],
)
def test_incomplete_or_extra_ui_data_is_rejected_without_filling_default_labels(change: str) -> None:
    value, dataset, plan, ledger, clock = submission()
    annotation = value["answers"][0]["items"]["E1"]
    if change == "missing_item":
        value["answers"][0]["items"].pop("E1")
    elif change == "missing_answer":
        value["answers"].pop()
    elif change == "duplicate_answer":
        value["answers"][1] = deepcopy(value["answers"][0])
    elif change == "label_hint":
        value["answers"][0]["item"] = "E1"
    elif change == "truthy_label":
        annotation["violation"] = 1
    elif change == "truthy_uncertain":
        annotation["uncertain"] = "false"
    elif change == "false_severity":
        annotation["severity"] = 3
    elif change == "true_no_severity":
        annotation["violation"] = True
    elif change == "severity_bool":
        annotation.update(violation=True, severity=True)
    elif change == "extra_top":
        value["origin"] = "human_ui"
    elif change == "naive_time":
        value["submitted_at"] = "2026-10-21T01:00:00"
    else:
        value["submitted_at"] = (AT + timedelta(microseconds=1)).isoformat()
    with pytest.raises(CalibrationError):
        validate_submission(value, dataset=dataset, plan=plan, ledger=ledger, clock=clock)


@pytest.mark.parametrize(
    "field", ["owner_id", "reviewer_id", "plan_sha256", "dataset_sha256", "rubric_sha256", "payload_sha256", "batch_id"]
)
def test_whole_submission_cannot_be_reused_for_other_scope_version_or_displayed_batch(field: str) -> None:
    value, dataset, plan, ledger, clock = submission()
    value[field] = "f" * 64 if field.endswith("sha256") else "foreign"
    with pytest.raises(CalibrationError):
        validate_submission(value, dataset=dataset, plan=plan, ledger=ledger, clock=clock)


def test_unopened_batch_and_clock_regression_cannot_accept_a_submission() -> None:
    value, dataset, plan, ledger, clock = submission()
    with pytest.raises(CalibrationError):
        validate_submission(value, dataset=dataset, plan=plan, ledger=OpeningLedger(plan.sha256), clock=clock)
    clock.advance(timedelta(microseconds=-1))
    with pytest.raises(CalibrationError):
        validate_submission(value, dataset=dataset, plan=plan, ledger=ledger, clock=clock)


def test_all_fifteen_items_can_be_marked_independently_without_exposing_target_item() -> None:
    value, dataset, plan, ledger, clock = submission()
    for index, item in enumerate(ITEMS):
        value["answers"][0]["items"][item] = {"violation": True, "severity": index % 5 + 1, "uncertain": True}
    VALIDATOR.validate(value)
    assert validate_submission(value, dataset=dataset, plan=plan, ledger=ledger, clock=clock).verified_human_count == 0

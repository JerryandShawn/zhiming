"""Cryptographic protocol examples are synthetic; none represent a real human review."""

import hashlib
import hmac
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.timekit.clock import FrozenClock
from tools.calibration_v3.batches import blind_payload
from tools.calibration_v3.blind_payload_contract import blind_payload_digest
from tools.calibration_v3.daily import OpeningLedger, plan_open_batch
from tools.calibration_v3.human_provenance import (
    HmacHostVerifier,
    HumanLabelRecord,
    attestation_bytes,
    verify_human_record,
)
from tools.calibration_v3.models import ITEMS, CalibrationError, label_vector

from .calibration_toy_support_mod import toy_plan

TEST_KEY = b"synthetic-unit-test-verifier-only-000000000"
AT = datetime(2026, 10, 21, 1, tzinfo=UTC)


def protocol_record() -> tuple:
    dataset, plan = toy_plan()
    clock = FrozenClock(AT)
    opening = plan_open_batch(
        plan, OpeningLedger(plan.sha256), clock=clock, operation_id="test-open", expected_revision=0
    )
    record = HumanLabelRecord(
        "synthetic-protocol-only",
        plan.scope.owner_id,
        plan.scope.reviewer_id,
        plan.sha256,
        plan.dataset_sha256,
        plan.rubric_sha256,
        blind_payload_digest(blind_payload(dataset, plan, plan.batches[0])),
        plan.batches[0].id,
        plan.batches[0].refs[0].blind_id,
        label_vector({item: False for item in ITEMS}),
        AT,
        "human_ui",
        "review",
        "0" * 64,
    )
    signed = replace(record, signature=hmac.new(TEST_KEY, attestation_bytes(record), hashlib.sha256).hexdigest())
    return signed, plan, opening.ledger, clock, dataset


def test_no_verifier_or_self_reported_human_origin_cannot_establish_provenance() -> None:
    record, plan, ledger, clock, dataset = protocol_record()
    with pytest.raises(CalibrationError, match="unavailable"):
        verify_human_record(record, plan=plan, dataset=dataset, ledger=ledger, verifier=None, clock=clock)
    for origin in ("brain_ai", "model", "synthetic_test", "human", "imported"):
        with pytest.raises(CalibrationError, match="human_ui_origin_required"):
            replace(record, origin=origin)


def test_test_host_signature_binds_labels_without_claiming_a_physical_human_was_observed() -> None:
    record, plan, ledger, clock, dataset = protocol_record()
    result = verify_human_record(
        record, plan=plan, dataset=dataset, ledger=ledger, verifier=HmacHostVerifier(TEST_KEY), clock=clock
    )
    assert result.source_id == plan.batches[0].refs[0].sample_id
    assert "synthetic-unit-test" not in repr(HmacHostVerifier(TEST_KEY))
    tampered = replace(record, labels=label_vector({item: item == "E1" for item in ITEMS}))
    with pytest.raises(CalibrationError, match="attestation_failed"):
        verify_human_record(
            tampered, plan=plan, dataset=dataset, ledger=ledger, verifier=HmacHostVerifier(TEST_KEY), clock=clock
        )


@pytest.mark.parametrize(
    "field", ["owner_id", "reviewer_id", "plan_sha256", "dataset_sha256", "rubric_sha256", "payload_sha256"]
)
def test_host_attestation_is_not_transferable_to_other_scope_or_versions(field: str) -> None:
    record, plan, ledger, clock, dataset = protocol_record()
    changed = replace(record, **{field: "e" * 64 if field.endswith("sha256") else "foreign"})
    with pytest.raises(CalibrationError):
        verify_human_record(
            changed, plan=plan, dataset=dataset, ledger=ledger, verifier=HmacHostVerifier(TEST_KEY), clock=clock
        )


def test_unopened_blind_batch_and_future_or_preopening_labels_are_not_accepted() -> None:
    record, plan, ledger, clock, dataset = protocol_record()
    changes = [
        {"batch_id": plan.batches[1].id, "blind_id": plan.batches[1].refs[0].blind_id},
        {"reviewed_at": AT - timedelta(microseconds=1)},
        {"reviewed_at": AT + timedelta(microseconds=1)},
    ]
    for change in changes:
        changed = replace(record, **change)
        changed = replace(changed, signature=hmac.new(TEST_KEY, attestation_bytes(changed), hashlib.sha256).hexdigest())
        with pytest.raises(CalibrationError):
            verify_human_record(
                changed, plan=plan, dataset=dataset, ledger=ledger, verifier=HmacHostVerifier(TEST_KEY), clock=clock
            )


@pytest.mark.parametrize("result", [False, 1, "true", None])
def test_verifier_result_must_be_true_boolean_not_truthy_metadata(result: object) -> None:
    record, plan, ledger, clock, dataset = protocol_record()
    with pytest.raises(CalibrationError):
        verify_human_record(
            record, plan=plan, dataset=dataset, ledger=ledger, verifier=lambda raw, signature: result, clock=clock
        )


def test_incomplete_label_vector_and_naive_time_are_rejected_before_verification() -> None:
    record, _, _, _, _ = protocol_record()
    with pytest.raises(CalibrationError):
        replace(record, labels=record.labels[:-1])
    with pytest.raises(CalibrationError):
        replace(record, reviewed_at=datetime(2026, 10, 21, 1))

"""Aggregate tests with toy cryptographic observations, never real human or critic labels."""

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.timekit.clock import FrozenClock
from tools.calibration_v3.batches import blind_payload
from tools.calibration_v3.blind_payload_contract import blind_payload_digest
from tools.calibration_v3.critic_records import CalibrationProtocol, CriticObservation, input_digest
from tools.calibration_v3.daily import OpeningLedger, plan_open_batch
from tools.calibration_v3.human_provenance import HmacHostVerifier, HumanLabelRecord, attestation_bytes
from tools.calibration_v3.models import ITEMS, CalibrationError
from tools.calibration_v3.reporting import build_calibration_report

from .calibration_toy_support_mod import TOY_BODY, toy_plan

KEY = b"synthetic-report-test-host-key-only-00000000"
AT = datetime(2026, 10, 21, 1, tzinfo=UTC)


def test_missing_actual_critic_prompt_is_unbound_not_a_hash_of_the_design_document() -> None:
    dataset, plan = toy_plan()
    protocol = CalibrationProtocol(None, plan.rubric_sha256)
    assert not protocol.current
    report = build_calibration_report(dataset, plan, protocol=protocol, clock=FrozenClock(AT))
    assert report["protocol"]["prompt_sha256"] is None and report["mode"] == "record_only"
    sample = dataset.samples[0]
    with pytest.raises(CalibrationError):
        CriticObservation(
            sample.source_id,
            input_digest(dataset, sample),
            protocol,
            "d" * 64,
            sample.labels,
            tuple((item, 3) for item in ITEMS),
            "critic_trace",
        )


def inputs() -> tuple:
    dataset, plan = toy_plan()
    protocol = CalibrationProtocol("c" * 64, plan.rubric_sha256)
    clock, ledger = FrozenClock(AT), OpeningLedger(plan.sha256)
    for ordinal in range(5):
        ledger = plan_open_batch(
            plan, ledger, clock=clock, operation_id=f"toy-open-{ordinal}", expected_revision=ledger.revision
        ).ledger
        clock.advance(timedelta(days=1))
    selected = [sample for sample in dataset.samples if sample.item == "E1" and sample.group != "T"]
    humans, critics = [], []
    for sample in selected:
        batch = next(batch for batch in plan.batches if any(ref.sample_id == sample.source_id for ref in batch.refs))
        ref = next(ref for ref in batch.refs if ref.sample_id == sample.source_id)
        record = HumanLabelRecord(
            "toy-review-" + sample.source_id,
            plan.scope.owner_id,
            plan.scope.reviewer_id,
            plan.sha256,
            plan.dataset_sha256,
            plan.rubric_sha256,
            blind_payload_digest(blind_payload(dataset, plan, batch)),
            batch.id,
            ref.blind_id,
            sample.labels,
            clock.now(),
            "human_ui",
            "review",
            "0" * 64,
        )
        humans.append(replace(record, signature=hmac.new(KEY, attestation_bytes(record), hashlib.sha256).hexdigest()))
        critics.append(
            CriticObservation(
                sample.source_id,
                input_digest(dataset, sample),
                protocol,
                "d" * 64,
                sample.labels,
                tuple((item, 3) for item in ITEMS),
                "synthetic_test",
            )
        )
    return dataset, plan, protocol, ledger, clock, tuple(humans), tuple(critics)


def test_absent_human_and_critic_evidence_is_explicitly_empty_and_record_only() -> None:
    dataset, plan = toy_plan()
    report = build_calibration_report(
        dataset, plan, protocol=CalibrationProtocol("c" * 64, plan.rubric_sha256), clock=FrozenClock(AT)
    )
    assert report["verified_human_reviewed_count"] == report["critic_observation_count"] == 0
    assert report["mode"] == "record_only" and report["runtime_revision_enabled"] is False
    assert report["macro_f1"] is None and len(report["items"]) == 15
    for row in report["items"]:
        assert row["state"] == "record_only"
        assert row["kappa_human"]["metrics"]["kappa"] is None
        assert row["kappa_critic_effective"]["metrics"]["kappa"] is None
    assert TOY_BODY not in json.dumps(report) and "toy-rationale" not in json.dumps(report)


def test_dual_kappas_bootstrap_are_separate_but_four_perfect_pairs_cannot_enable_revision() -> None:
    dataset, plan, protocol, ledger, clock, humans, critics = inputs()
    report = build_calibration_report(
        dataset,
        plan,
        protocol=protocol,
        ledger=ledger,
        clock=clock,
        human_records=humans,
        critic_records=critics,
        verifier=HmacHostVerifier(KEY),
    )
    item = next(row for row in report["items"] if row["item"] == "E1")
    for name in ("kappa_human", "kappa_critic_effective", "kappa_critic_raw"):
        assert item[name]["metrics"]["kappa"] == 1
        assert item[name]["kappa_bootstrap95"]["draws"] == 2000
        assert item[name]["kappa_bootstrap95"]["interval95"] == (1.0, 1.0)
    assert item["state"] == "record_only"
    assert "human_rubric_evidence_insufficient" in item["reasons"]
    assert "brain25_alone_requires_merged_baseline_and_seeded_set" in item["reasons"]
    assert report["runtime_configuration_writes"] == 0


def test_confidence_one_is_raw_violation_but_not_effective_trigger_and_j8_j9_never_trigger() -> None:
    dataset, plan, protocol, _, _, _, critics = inputs()
    changed = replace(critics[0], confidence=tuple((item, 1) for item in ITEMS))
    assert any(dict(changed.labels).values())
    assert not any(changed.effective(item) for item in ITEMS)
    sample = dataset.samples[0]
    every = replace(
        critics[0],
        sample_id=sample.source_id,
        input_sha256=input_digest(dataset, sample),
        labels=tuple((item, True) for item in ITEMS),
    )
    assert not every.effective("J8") and not every.effective("J9")
    assert protocol.rubric_sha256 == plan.rubric_sha256


def test_unadjudicated_disagreement_is_missing_gold_not_overwritten_with_brain_label() -> None:
    dataset, plan, protocol, ledger, clock, humans, critics = inputs()
    first = humans[0]
    changed = replace(first, labels=tuple((item, not value if item == "E1" else value) for item, value in first.labels))
    changed = replace(changed, signature=hmac.new(KEY, attestation_bytes(changed), hashlib.sha256).hexdigest())
    report = build_calibration_report(
        dataset,
        plan,
        protocol=protocol,
        ledger=ledger,
        clock=clock,
        human_records=(changed, *humans[1:]),
        critic_records=critics,
        verifier=HmacHostVerifier(KEY),
    )
    item = next(row for row in report["items"] if row["item"] == "E1")
    assert item["unresolved_count"] == 1 and item["kappa_critic_effective"]["metrics"]["paired_count"] == 3
    assert "unadjudicated_or_uncertain_human_labels" in item["reasons"]


def test_unverified_human_or_changed_critic_input_cannot_be_a_calibration_report() -> None:
    dataset, plan, protocol, ledger, clock, humans, critics = inputs()
    with pytest.raises(CalibrationError):
        build_calibration_report(dataset, plan, protocol=protocol, ledger=ledger, clock=clock, human_records=humans)
    with pytest.raises(CalibrationError):
        build_calibration_report(
            dataset,
            plan,
            protocol=protocol,
            ledger=ledger,
            clock=clock,
            critic_records=(replace(critics[0], input_sha256="f" * 64),),
        )

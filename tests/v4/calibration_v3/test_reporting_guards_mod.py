"""Tamper/replay/adjudication paths use only independently constructed toy labels."""

import hashlib
import hmac
from dataclasses import replace
from datetime import timedelta

import pytest

from tools.calibration_v3.critic_records import CalibrationProtocol
from tools.calibration_v3.human_provenance import HmacHostVerifier, attestation_bytes
from tools.calibration_v3.models import CalibrationError
from tools.calibration_v3.reporting import build_calibration_report

from .test_reporting_mod import KEY, inputs


def report_case(humans: tuple | None = None, critics: tuple | None = None) -> dict:
    dataset, plan, protocol, ledger, clock, original_humans, original_critics = inputs()
    return build_calibration_report(
        dataset,
        plan,
        protocol=protocol,
        ledger=ledger,
        clock=clock,
        human_records=original_humans if humans is None else humans,
        critic_records=original_critics if critics is None else critics,
        verifier=HmacHostVerifier(KEY),
    )


def signed(record: object) -> object:
    return replace(record, signature=hmac.new(KEY, attestation_bytes(record), hashlib.sha256).hexdigest())


def test_identical_observation_replay_does_not_inflate_human_or_critic_denominators() -> None:
    *_, humans, critics = inputs()
    report = report_case((*humans, humans[0]), (*critics, critics[0]))
    assert report["verified_human_reviewed_count"] == report["critic_observation_count"] == 4


def test_same_human_operation_cannot_replace_its_content_even_with_a_valid_host_signature() -> None:
    *_, humans, _ = inputs()
    altered = signed(replace(humans[0], uncertain_items=("E1",)))
    with pytest.raises(CalibrationError, match="operation_changed"):
        report_case((*humans, altered))


def test_two_distinct_reviews_of_one_case_are_not_silently_overwritten() -> None:
    *_, humans, _ = inputs()
    duplicate = signed(replace(humans[0], record_id="other-toy-operation"))
    with pytest.raises(CalibrationError, match="stage_duplicate"):
        report_case((*humans, duplicate))


def test_adjudication_requires_prior_authenticated_review_and_nonregressing_time() -> None:
    *_, humans, _ = inputs()
    adjudication = signed(replace(humans[0], record_id="toy-adjudication", stage="adjudication"))
    with pytest.raises(CalibrationError, match="prior_review"):
        report_case((adjudication, *humans[1:]))
    too_early = signed(replace(adjudication, reviewed_at=adjudication.reviewed_at - timedelta(microseconds=1)))
    with pytest.raises(CalibrationError, match="prior_review"):
        report_case((*humans, too_early))


def test_final_adjudication_resolves_disagreement_without_changing_the_brain_reference_kappa() -> None:
    *_, humans, _ = inputs()
    changed = signed(
        replace(
            humans[0], labels=tuple((item, not value if item == "E1" else value) for item, value in humans[0].labels)
        )
    )
    adjudication = signed(replace(changed, record_id="toy-final", stage="adjudication"))
    report = report_case((changed, *humans[1:], adjudication))
    item = next(row for row in report["items"] if row["item"] == "E1")
    assert item["unresolved_count"] == 0
    assert item["kappa_human"]["metrics"]["kappa"] < 1
    assert item["kappa_critic_effective"]["metrics"]["paired_count"] == 4
    assert item["kappa_critic_effective"]["metrics"]["kappa"] < 1
    assert item["state"] == "record_only"


def test_uncertain_final_adjudication_remains_missing_gold_and_cannot_be_a_clean_pair() -> None:
    *_, humans, _ = inputs()
    adjudication = signed(
        replace(humans[0], record_id="toy-still-uncertain", stage="adjudication", uncertain_items=("E1",))
    )
    report = report_case((*humans, adjudication))
    item = next(row for row in report["items"] if row["item"] == "E1")
    assert item["unresolved_count"] == 1 and item["kappa_critic_effective"]["metrics"]["paired_count"] == 3


def test_changed_critic_artifact_of_same_sample_is_a_conflict_not_a_new_vote() -> None:
    *_, critics = inputs()
    with pytest.raises(CalibrationError, match="observation_conflict"):
        report_case(critics=(*critics, replace(critics[0], artifact_sha256="e" * 64)))


@pytest.mark.parametrize("update", [{"model": "other"}, {"effort": "low"}, {"prompt_version": "2.0.1"}])
def test_model_effort_or_prompt_version_change_requires_recalibration(update: dict) -> None:
    dataset, plan, protocol, _, clock, _, _ = inputs()
    changed = replace(protocol, **update)
    report = build_calibration_report(dataset, plan, protocol=changed, clock=clock)
    assert all("protocol_requires_recalibration" in item["reasons"] for item in report["items"])
    assert not report["runtime_revision_enabled"]


def test_a_protocol_with_a_different_rubric_cannot_reuse_the_existing_plan() -> None:
    dataset, plan, protocol, _, clock, _, _ = inputs()
    with pytest.raises(CalibrationError, match="binding_mismatch"):
        build_calibration_report(dataset, plan, protocol=replace(protocol, rubric_sha256="f" * 64), clock=clock)


def test_untyped_metadata_is_not_a_verified_observation_or_protocol() -> None:
    dataset, plan, protocol, _, clock, _, _ = inputs()
    for key in ("human_records", "critic_records"):
        with pytest.raises(CalibrationError):
            build_calibration_report(dataset, plan, protocol=protocol, clock=clock, **{key: ({"origin": "human"},)})
    with pytest.raises(CalibrationError):
        build_calibration_report(dataset, plan, protocol={"model": "k3-256k"}, clock=clock)
    assert CalibrationProtocol(None, plan.rubric_sha256).current is False

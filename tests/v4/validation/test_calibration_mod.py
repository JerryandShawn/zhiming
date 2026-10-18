"""Hand-computed statistics and synthetic provenance fixtures; no production labels are fabricated."""

from __future__ import annotations

from dataclasses import replace

import pytest

from mingjing_core.validation.calibration import (
    CalibrationIdentity,
    CalibrationProvenance,
    CalibrationSample,
    binary_metrics,
    calculate_calibration,
    wilson_interval,
)
from mingjing_core.validation.critic_contracts import ITEM_TYPES


def synthetic_samples(count: int = 60) -> list[CalibrationSample]:
    return [
        CalibrationSample(
            f"synthetic-{index}",
            {item: index % 2 == 0 for item in ITEM_TYPES},
            {item: index % 2 == 0 for item in ITEM_TYPES},
        )
        for index in range(count)
    ]


def synthetic_provenance(samples: list[CalibrationSample]) -> CalibrationProvenance:
    ids = [sample.id for sample in samples]
    return CalibrationProvenance("synthetic-test-only", frozenset(ids), frozenset(ids[:15]), frozenset(ids[:10]))


def test_confusion_matrix_sensitivity_specificity_kappa_and_f1_match_hand_calculation() -> None:
    metrics = binary_metrics([True] * 10 + [False] * 10, [True] * 8 + [False] * 2 + [True] + [False] * 9)
    assert (metrics.true_positive, metrics.true_negative, metrics.false_positive, metrics.false_negative) == (
        8,
        9,
        1,
        2,
    )
    assert (metrics.positives, metrics.negatives, metrics.paired_count) == (10, 10, 20)
    assert metrics.sensitivity == 0.8 and metrics.specificity == 0.9
    assert metrics.agreement == 0.85 and metrics.kappa == pytest.approx(0.7)
    assert metrics.f1 == pytest.approx(16 / 19)
    assert metrics.agreement_wilson95 == pytest.approx(wilson_interval(17, 20))


def test_wilson_known_small_sample_and_boundary_cases() -> None:
    assert wilson_interval(16, 20) == pytest.approx((0.5839825677, 0.9193423374))
    assert wilson_interval(0, 20)[0] == 0
    assert wilson_interval(20, 20)[1] == 1
    assert wilson_interval(0, 0) is None
    for wins, count in [(0, 1), (1, 1), (9, 10), (1, 1000)]:
        low, high = wilson_interval(wins, count)
        assert 0 <= low <= wins / count <= high <= 1


@pytest.mark.parametrize("successes,total", [(-1, 20), (21, 20), (1, -1), (True, 10), (1.0, 10)])
def test_wilson_rejects_invalid_or_coerced_counts(successes: int, total: int) -> None:
    with pytest.raises(ValueError):
        wilson_interval(successes, total)


def test_no_pairs_or_degenerate_kappa_never_becomes_perfect_calibration() -> None:
    empty = binary_metrics([], [])
    assert empty.kappa is empty.sensitivity is empty.specificity is empty.agreement is empty.f1 is None
    negative = binary_metrics([False] * 20, [False] * 20)
    assert negative.agreement == 1 and negative.kappa is None and negative.sensitivity is None
    positive = binary_metrics([True] * 20, [True] * 20)
    assert positive.kappa is None and positive.specificity is None
    assert binary_metrics([True, False], [False, True]).kappa == -1


@pytest.mark.parametrize("actual,predicted", [([True], []), ([1], [True]), ([False], [0])])
def test_binary_metrics_reject_missing_or_non_boolean_labels(actual: list[bool], predicted: list[bool]) -> None:
    with pytest.raises(ValueError):
        binary_metrics(actual, predicted)


def test_only_complete_provenance_attested_sixty_sample_report_can_enable_items() -> None:
    samples = synthetic_samples()
    report = calculate_calibration(
        samples, identity=CalibrationIdentity("synthetic-test-only"), provenance=synthetic_provenance(samples)
    )
    assert report.complete and report.provenance_verified and report.macro_f1 == 1
    assert len(report.items) == 15 and report.user_reviewed_count == 15
    assert all(report.state_for(item) == "revision_enabled" for item in ITEM_TYPES if item not in {"J8", "J9"})
    assert report.state_for("J8") == report.state_for("J9") == report.state_for("unknown") == "record_only"
    serialized = report.as_dict()
    assert len(serialized["items"]) == 15 and serialized["identity"]["model"] == "k3-256k"


@pytest.mark.parametrize("count", [0, 1, 20, 59, 60])
def test_synthetic_scores_without_human_provenance_are_record_only(count: int) -> None:
    report = calculate_calibration(synthetic_samples(count), identity=CalibrationIdentity("unlabeled-candidate"))
    assert not report.provenance_verified
    assert all(report.state_for(item) == "record_only" for item in ITEM_TYPES)


def test_one_missing_item_prevents_complete_corpus_gate_without_inventing_negative_labels() -> None:
    samples = synthetic_samples()
    original = samples[0]
    partial = dict(original.human_labels)
    partial.pop("E1")
    samples[0] = replace(original, human_labels=partial)
    report = calculate_calibration(
        samples, identity=CalibrationIdentity("partial"), provenance=synthetic_provenance(samples)
    )
    assert not report.complete
    e1 = next(row for row in report.items if row.item == "E1")
    assert e1.missing_labels == 1 and e1.metrics.paired_count == 59
    assert report.macro_f1 is None and report.macro_defined_items == 15
    assert all(report.state_for(item) == "record_only" for item in ITEM_TYPES)


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "k3"),
        ("effort", "low"),
        ("critic_prompt_version", "1.0.0"),
        ("rubric_version", "v1"),
    ],
)
def test_protocol_identity_drift_requires_recalibration(field: str, value: str) -> None:
    samples = synthetic_samples()
    identity = replace(CalibrationIdentity("old"), **{field: value})
    report = calculate_calibration(samples, identity=identity, provenance=synthetic_provenance(samples))
    assert all(report.state_for(item) == "record_only" for item in ITEM_TYPES)


@pytest.mark.parametrize(
    "field,value",
    [
        ("brain_labeled_ids", frozenset()),
        ("user_reviewed_ids", frozenset()),
        ("user_random_ids", frozenset()),
        ("known_disagreements", frozenset({"synthetic-0"})),
    ],
)
def test_missing_human_review_or_unresolved_disagreement_prevents_enablement(field: str, value: frozenset[str]) -> None:
    samples = synthetic_samples()
    provenance = replace(synthetic_provenance(samples), **{field: value})
    report = calculate_calibration(samples, identity=CalibrationIdentity("test"), provenance=provenance)
    assert all(report.state_for(item) == "record_only" for item in ITEM_TYPES)


def test_failed_seeded_defect_item_is_downgraded_and_macro_f1_is_item_macro() -> None:
    samples = synthetic_samples()
    altered = [replace(sample, critic_labels=dict(sample.critic_labels, E1=False)) for sample in samples]
    report = calculate_calibration(
        altered,
        identity=CalibrationIdentity("test"),
        provenance=synthetic_provenance(altered),
        defect_status={"J1": False},
    )
    assert report.macro_f1 == pytest.approx(14 / 15)
    assert report.state_for("E1") == report.state_for("J1") == "record_only"
    assert next(row for row in report.items if row.item == "J1").reason == "seeded_or_laxity_test_failed"


def test_judgment_threshold_requires_at_least_five_of_each_class() -> None:
    samples = [
        CalibrationSample(f"synthetic-{i}", {item: i < 4 for item in ITEM_TYPES}, {item: i < 4 for item in ITEM_TYPES})
        for i in range(60)
    ]
    report = calculate_calibration(
        samples, identity=CalibrationIdentity("few-positive"), provenance=synthetic_provenance(samples)
    )
    assert report.state_for("J1") == "record_only"
    assert report.state_for("E1") == "revision_enabled"


def test_sample_label_maps_are_immutable_defensive_copies_and_duplicates_are_rejected() -> None:
    labels = {"E1": True}
    sample = CalibrationSample("one", labels, labels)
    labels.clear()
    assert sample.human_labels == {"E1": True}
    with pytest.raises(TypeError):
        sample.human_labels["E1"] = False
    with pytest.raises(ValueError, match="unique"):
        calculate_calibration([sample, sample], identity=CalibrationIdentity("duplicate"))
    with pytest.raises(ValueError, match="unknown"):
        CalibrationSample("x", {"NEW": False}, {})
    with pytest.raises(ValueError, match="actual booleans"):
        CalibrationSample("x", {"E1": 1}, {})


@pytest.mark.parametrize("field", ["version", "model", "effort", "critic_prompt_version", "rubric_version"])
@pytest.mark.parametrize("value", ["", "  ", None, 1])
def test_identity_requires_every_version_and_model_field(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="nonempty"):
        replace(CalibrationIdentity("valid"), **{field: value})


def test_missing_pairs_or_undefined_item_f1_are_not_silently_filled_with_zero() -> None:
    no_pairs = calculate_calibration([CalibrationSample("missing", {}, {})], identity=CalibrationIdentity("missing"))
    assert no_pairs.macro_f1 is None and no_pairs.macro_defined_items == 0
    zeros = [
        CalibrationSample(f"zero-{i}", dict.fromkeys(ITEM_TYPES, False), dict.fromkeys(ITEM_TYPES, False))
        for i in range(60)
    ]
    report = calculate_calibration(zeros, identity=CalibrationIdentity("all-negative"))
    assert report.macro_f1 is None and report.macro_defined_items == 0
    assert all(row.metrics.agreement == 1 and row.metrics.kappa is None for row in report.items)
    historical = calculate_calibration(synthetic_samples(20), identity=CalibrationIdentity("v1-historical"))
    assert historical.macro_f1 == 1 and historical.macro_defined_items == 15 and not historical.complete

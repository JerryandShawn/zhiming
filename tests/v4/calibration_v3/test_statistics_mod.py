"""Known binary tables and seeded bootstrap properties, without hard-case answer keys."""

import pytest

from tools.calibration_v3.models import CalibrationError
from tools.calibration_v3.statistics import binary_metrics, bootstrap_kappa, wilson95


def test_hand_computed_one_in_each_confusion_cell() -> None:
    metrics = binary_metrics([True, True, False, False], [True, False, True, False])
    assert (metrics.true_positive, metrics.true_negative, metrics.false_positive, metrics.false_negative) == (
        1,
        1,
        1,
        1,
    )
    assert metrics.kappa == 0 and metrics.agreement == metrics.sensitivity == metrics.specificity == metrics.f1 == 0.5
    assert metrics.agreement_wilson95 == pytest.approx((0.15003898915214947, 0.8499610108478506))


def test_balanced_perfect_labels_have_kappa_one_and_reproducible_answer_bootstrap() -> None:
    actual = [True] * 6 + [False] * 6
    first = bootstrap_kappa(actual, actual, seed=12345)
    assert first == bootstrap_kappa(actual, actual, seed=12345)
    assert first.draws == 2000 and 0 < first.defined_draws <= 2000
    assert first.interval95 == (1.0, 1.0) and first.resampling_unit == "paired_answer"


@pytest.mark.parametrize("actual,guess", [([], []), ([True] * 12, [True] * 12), ([False] * 12, [False] * 12)])
def test_empty_or_single_class_agreement_is_not_defined_kappa_evidence(actual: list, guess: list) -> None:
    metrics = binary_metrics(actual, guess)
    assert metrics.kappa is None
    result = bootstrap_kappa(actual, guess, seed=12345)
    assert result.interval95 is None and result.defined_draws == 0


def test_completely_opposed_balanced_labels_have_negative_kappa_with_bounded_interval() -> None:
    actual = [True] * 8 + [False] * 8
    guess = [not value for value in actual]
    assert binary_metrics(actual, guess).kappa == -1
    result = bootstrap_kappa(actual, guess, seed=2104)
    assert -1 <= result.interval95[0] <= result.interval95[1] <= 1
    assert result.interval95[1] < 0


@pytest.mark.parametrize("actual,guess", [([True], []), ([1], [True]), ([False], [0]), ([None], [False])])
def test_labels_are_strict_booleans_and_remain_paired(actual: list, guess: list) -> None:
    with pytest.raises(CalibrationError):
        binary_metrics(actual, guess)


@pytest.mark.parametrize("success,total", [(True, 4), (1, True), (-1, 4), (5, 4), (1, -1)])
def test_wilson_rejects_invalid_counts(success: object, total: object) -> None:
    with pytest.raises(CalibrationError):
        wilson95(success, total)


def test_zero_total_and_point_estimate_are_not_rounded_into_a_threshold() -> None:
    assert wilson95(0, 0) is None
    interval = wilson95(8, 10)
    assert interval[0] < 0.6 and interval[1] > 0.9
    assert binary_metrics([True, False], [True, False]).positives == 1


@pytest.mark.parametrize("draws", [0, 1, 1999, 2001, True])
def test_the_required_bootstrap_count_is_not_silently_lowered(draws: object) -> None:
    with pytest.raises(CalibrationError):
        bootstrap_kappa([True, False], [True, False], seed=123, draws=draws)

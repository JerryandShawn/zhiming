"""Independent algebraic oracles; no brain sample text, labels or blind mappings."""

from fractions import Fraction
from itertools import product

import pytest

from tools.calibration_v3.statistics import binary_metrics, wilson95


def test_all_small_contingency_tables_match_the_determinant_kappa_identity() -> None:
    """Check 6561 tables using the determinant identity rather than observed/chance agreement."""
    for true_positive, false_negative, false_positive, true_negative in product(range(9), repeat=4):
        actual = [True] * (true_positive + false_negative) + [False] * (false_positive + true_negative)
        predicted = (
            [True] * true_positive + [False] * false_negative + [True] * false_positive + [False] * true_negative
        )
        metrics = binary_metrics(actual, predicted)
        numerator = 2 * (true_positive * true_negative - false_positive * false_negative)
        denominator = (true_positive + false_negative) * (false_negative + true_negative) + (
            true_positive + false_positive
        ) * (false_positive + true_negative)
        if denominator == 0:
            assert metrics.kappa is None
        else:
            assert metrics.kappa == pytest.approx(float(Fraction(numerator, denominator)), abs=1e-14)
        assert binary_metrics(predicted, actual).kappa == metrics.kappa
        assert (
            binary_metrics([not value for value in actual], [not value for value in predicted]).kappa == metrics.kappa
        )


def test_wilson_endpoints_invert_the_score_test_and_are_complement_symmetric() -> None:
    """Check 5150 nonempty binomial counts, without copying the quadratic interval formula."""
    z_squared = 1.959963984540054**2
    for total in range(1, 101):
        for successes in range(total + 1):
            low, high = wilson95(successes, total)
            reverse_low, reverse_high = wilson95(total - successes, total)
            estimate = successes / total
            assert 0 <= low <= estimate <= high <= 1
            assert (low, high) == pytest.approx((1 - reverse_high, 1 - reverse_low), abs=1e-14)
            if successes > 0:
                assert total * (estimate - low) ** 2 / (low * (1 - low)) == pytest.approx(z_squared, rel=1e-10)
            else:
                assert low == pytest.approx(0, abs=1e-14)
            if successes < total:
                assert total * (estimate - high) ** 2 / (high * (1 - high)) == pytest.approx(z_squared, rel=1e-10)
            else:
                assert high == pytest.approx(1, abs=1e-14)

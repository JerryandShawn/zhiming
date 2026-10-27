"""Paired answer-level binary statistics; undefined or small samples never become success."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from random import Random

from .models import CalibrationError


@dataclass(frozen=True)
class BinaryMetrics:
    paired_count: int
    positives: int
    negatives: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    sensitivity: float | None
    specificity: float | None
    agreement: float | None
    kappa: float | None
    f1: float | None
    agreement_wilson95: tuple[float, float] | None


@dataclass(frozen=True)
class BootstrapKappa:
    interval95: tuple[float, float] | None
    draws: int
    defined_draws: int
    seed: int
    resampling_unit: str = "paired_answer"


def wilson95(successes: int, total: int) -> tuple[float, float] | None:
    if type(successes) is not int or type(total) is not int or not 0 <= successes <= total:
        raise CalibrationError("wilson_counts_invalid")
    if total == 0:
        return None
    z, n, p = 1.959963984540054, total, successes / total
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    lower = 0.0 if successes == 0 else max(0.0, centre - half)
    upper = 1.0 if successes == total else min(1.0, centre + half)
    return lower, upper


def binary_metrics(reference: Sequence[bool], predicted: Sequence[bool]) -> BinaryMetrics:
    if len(reference) != len(predicted) or any(type(value) is not bool for value in (*reference, *predicted)):
        raise CalibrationError("paired_boolean_labels_required")
    pairs = tuple(zip(reference, predicted, strict=True))
    tp = sum(actual and guess for actual, guess in pairs)
    tn = sum(not actual and not guess for actual, guess in pairs)
    fp = sum(not actual and guess for actual, guess in pairs)
    fn = sum(actual and not guess for actual, guess in pairs)
    count, positive, negative = len(pairs), tp + fn, tn + fp
    chance = positive * (tp + fp) + negative * (tn + fn)
    denominator = count * count - chance
    return BinaryMetrics(
        count,
        positive,
        negative,
        tp,
        tn,
        fp,
        fn,
        tp / positive if positive else None,
        tn / negative if negative else None,
        (tp + tn) / count if count else None,
        (count * (tp + tn) - chance) / denominator if denominator else None,
        2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        wilson95(tp + tn, count),
    )


def _quantile(values: list[float], fraction: float) -> float:
    location = (len(values) - 1) * fraction
    lower, upper = math.floor(location), math.ceil(location)
    return values[lower] + (values[upper] - values[lower]) * (location - lower)


def bootstrap_kappa(
    reference: Sequence[bool], predicted: Sequence[bool], *, seed: int, draws: int = 2000
) -> BootstrapKappa:
    metrics = binary_metrics(reference, predicted)
    if type(seed) is not int or type(draws) is not int or draws != 2000:
        raise CalibrationError("fixed_2000_bootstrap_required")
    if metrics.paired_count == 0 or metrics.kappa is None:
        return BootstrapKappa(None, draws, 0, seed)
    rng, values = Random(seed), []
    for _ in range(draws):
        indices = [rng.randrange(metrics.paired_count) for _ in range(metrics.paired_count)]
        point = binary_metrics([reference[index] for index in indices], [predicted[index] for index in indices]).kappa
        if point is not None:
            values.append(point)
    values.sort()
    interval = (_quantile(values, 0.025), _quantile(values, 0.975)) if values else None
    return BootstrapKappa(interval, draws, len(values), seed)

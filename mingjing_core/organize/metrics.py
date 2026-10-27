"""Dependency-free evaluation; labels are supplied by an independent annotation set."""

from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Sequence
from dataclasses import asdict, dataclass
from fractions import Fraction


def _same_length(*values: Sequence[object]) -> int:
    lengths = {len(value) for value in values}
    if len(lengths) != 1:
        raise ValueError("evaluation arrays must have equal lengths")
    return next(iter(lengths), 0)


def classification_accuracy(
    expected: Sequence[Hashable],
    predicted: Sequence[Hashable],
    clear_assignment: Sequence[bool] | None = None,
) -> float:
    """Score only explicit annotations; do not reward abstentions on ambiguous items."""
    count = _same_length(expected, predicted)
    mask = [True] * count if clear_assignment is None else clear_assignment
    _same_length(expected, mask)
    selected = [
        (actual, guess)
        for actual, guess, keep in zip(expected, predicted, mask, strict=True)
        if keep
    ]
    if not selected:
        raise ValueError("accuracy requires at least one explicitly annotated item")
    return sum(actual == guess for actual, guess in selected) / len(selected)


def _pairs(size: int) -> int:
    return size * (size - 1) // 2


def adjusted_rand_index(
    expected: Sequence[Hashable], predicted: Sequence[Hashable]
) -> float:
    """Hubert-Arabie ARI, exact integer counting and chance correction.

    Empty/singleton partitions and equivalent degenerate partitions score 1.0.
    Cluster names do not need to match. Unlike raw Rand accuracy, chance-level
    partitions score near zero and can receive a negative score.
    """
    count = _same_length(expected, predicted)
    if count < 2:
        return 1.0
    rows = Counter(expected)
    columns = Counter(predicted)
    cells = Counter(zip(expected, predicted, strict=True))
    agreements = sum(_pairs(size) for size in cells.values())
    row_pairs = sum(_pairs(size) for size in rows.values())
    column_pairs = sum(_pairs(size) for size in columns.values())
    chance = Fraction(row_pairs * column_pairs, _pairs(count))
    maximum = Fraction(row_pairs + column_pairs, 2)
    denominator = maximum - chance
    return 1.0 if denominator == 0 else float((agreements - chance) / denominator)


@dataclass(frozen=True)
class AssignmentMetrics:
    total: int
    clear_count: int
    ambiguous_count: int
    correct_clear: int
    space_accuracy: float
    topic_ari: float
    review_count: int
    low_confidence_count: int
    low_confidence_without_review: int

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


def evaluate_assignments(
    expected_space: Sequence[Hashable],
    predicted_space: Sequence[Hashable],
    expected_topic: Sequence[Hashable],
    predicted_topic: Sequence[Hashable],
    clear_assignment: Sequence[bool],
    needs_review: Sequence[bool],
    low_confidence: Sequence[bool] | None = None,
) -> AssignmentMetrics:
    """Report space accuracy on clear items and topic ARI on *all* supplied items.

    A caller reporting clear-only ARI must explicitly filter every array and say
    so in its report. Low confidence is a separate input: a correct default-space
    guess does not excuse a missing review flag.
    """
    count = _same_length(
        expected_space,
        predicted_space,
        expected_topic,
        predicted_topic,
        clear_assignment,
        needs_review,
    )
    uncertain = (
        [not flag for flag in clear_assignment]
        if low_confidence is None
        else low_confidence
    )
    _same_length(expected_space, uncertain)
    correct = sum(
        actual == guess and keep
        for actual, guess, keep in zip(
            expected_space, predicted_space, clear_assignment, strict=True
        )
    )
    return AssignmentMetrics(
        total=count,
        clear_count=sum(clear_assignment),
        ambiguous_count=count - sum(clear_assignment),
        correct_clear=correct,
        space_accuracy=classification_accuracy(
            expected_space, predicted_space, clear_assignment
        ),
        topic_ari=adjusted_rand_index(expected_topic, predicted_topic),
        review_count=sum(needs_review),
        low_confidence_count=sum(uncertain),
        low_confidence_without_review=sum(
            low and not review
            for low, review in zip(uncertain, needs_review, strict=True)
        ),
    )

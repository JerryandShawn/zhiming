"""Independent metric examples and invariants; no classification implementation imports."""

from __future__ import annotations

import json
import random
import runpy
from collections import Counter
from datetime import UTC, datetime
from fractions import Fraction
from itertools import combinations
from pathlib import Path

import pytest

from mingjing_core.organize.metrics import (
    adjusted_rand_index,
    classification_accuracy,
    evaluate_assignments,
)


def _pairwise_oracle(expected: list[int], predicted: list[int]) -> float:
    pairs = list(combinations(range(len(expected)), 2))
    if not pairs:
        return 1.0
    true_pairs = sum(expected[left] == expected[right] for left, right in pairs)
    predicted_pairs = sum(predicted[left] == predicted[right] for left, right in pairs)
    both = sum(
        expected[left] == expected[right] and predicted[left] == predicted[right]
        for left, right in pairs
    )
    chance = Fraction(true_pairs * predicted_pairs, len(pairs))
    upper = Fraction(true_pairs + predicted_pairs, 2)
    return 1.0 if upper == chance else float((both - chance) / (upper - chance))


@pytest.mark.parametrize(
    ("expected", "predicted", "score"),
    [
        ([], [], 1.0),
        (["x"], ["y"], 1.0),
        ([0, 0, 1, 1], ["b", "b", "a", "a"], 1.0),
        ([0, 0, 1, 1], [0, 1, 0, 1], -0.5),
        ([0, 0, 1, 1], [0, 0, 0, 1], 0.0),
        ([0, 0, 0], [1, 2, 3], 0.0),
        ([0, 0, 0], [4, 4, 4], 1.0),
        ([0, 1, 2], [3, 4, 5], 1.0),
    ],
)
def test_ari_known_partitions(
    expected: list[object], predicted: list[object], score: float
) -> None:
    assert adjusted_rand_index(expected, predicted) == pytest.approx(score)


def test_ari_matches_independent_pair_count_oracle_and_permutation() -> None:
    rng = random.Random(8821)
    for _ in range(100):
        size = rng.randrange(2, 15)
        expected = [rng.randrange(4) for _ in range(size)]
        predicted = [rng.randrange(5) for _ in range(size)]
        score = adjusted_rand_index(expected, predicted)
        assert score == pytest.approx(_pairwise_oracle(expected, predicted))
        assert score == pytest.approx(adjusted_rand_index(predicted, expected))
        shuffled = list(zip(expected, predicted, strict=True))
        rng.shuffle(shuffled)
        assert score == pytest.approx(
            adjusted_rand_index([p[0] for p in shuffled], [p[1] for p in shuffled])
        )


def test_ari_large_equivalent_partitions_has_no_overflow() -> None:
    expected = [index % 41 for index in range(100_000)]
    predicted = [f"renamed-{index % 41}" for index in range(100_000)]
    assert adjusted_rand_index(expected, predicted) == 1.0


def test_accuracy_masks_ambiguous_without_turning_defaults_into_correct_guesses() -> (
    None
):
    assert (
        classification_accuracy(
            ["career", "daily", "family"], ["career", "daily", "daily"]
        )
        == 2 / 3
    )
    assert (
        classification_accuracy(
            ["career", "daily", "family"], ["career", "daily", "daily"], [1, 0, 1]
        )
        == 0.5
    )


@pytest.mark.parametrize("method", [adjusted_rand_index, classification_accuracy])
def test_metrics_reject_length_mismatch(method: object) -> None:
    with pytest.raises(ValueError, match="equal lengths"):
        method([0, 1], [0])


def test_empty_accuracy_cannot_silently_pass() -> None:
    with pytest.raises(ValueError, match="at least one"):
        classification_accuracy([], [])
    with pytest.raises(ValueError, match="at least one"):
        classification_accuracy(["daily"], ["daily"], [False])
    with pytest.raises(ValueError, match="equal lengths"):
        classification_accuracy(["daily"], ["daily"], [])


def test_report_counts_low_confidence_even_when_the_default_guess_is_correct() -> None:
    report = evaluate_assignments(
        ["career", "daily", "family"],
        ["career", "daily", "daily"],
        ["a", "b", "c"],
        ["x", "y", "z"],
        [True, False, True],
        [False, False, True],
        [False, True, True],
    )
    assert report.as_dict() == {
        "total": 3,
        "clear_count": 2,
        "ambiguous_count": 1,
        "correct_clear": 1,
        "space_accuracy": 0.5,
        "topic_ari": 1.0,
        "review_count": 1,
        "low_confidence_count": 2,
        "low_confidence_without_review": 1,
    }


def test_report_rejects_review_mask_truncation() -> None:
    with pytest.raises(ValueError, match="equal lengths"):
        evaluate_assignments([1], [1], [1], [1], [True], [], [False])
    with pytest.raises(ValueError, match="equal lengths"):
        evaluate_assignments([1], [1], [1], [1], [True], [False], [])


def test_corpus_integrity_and_independent_annotations() -> None:
    messages = json.loads(
        (Path(__file__).parent / "fixtures" / "history_600.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(messages) == len({item["id"] for item in messages}) == 600
    assert Counter(item["role"] for item in messages) == {"user": 300, "assistant": 300}
    assert (
        len(
            {
                datetime.fromtimestamp(item["at_ms"] / 1000, UTC).date()
                for item in messages
            }
        )
        == 30
    )
    assert [item["at_ms"] for item in messages] == sorted(
        item["at_ms"] for item in messages
    )
    assert sum(item["clear_assignment"] for item in messages) == 480
    assert len({item["expected_space"] for item in messages}) == 7
    assert (
        len({item["expected_topic"] for item in messages if item["clear_assignment"]})
        == 16
    )
    assert {item["owner_id"] for item in messages} == {"synthetic-owner"}
    assert {item["subject_id"] for item in messages} == {"synthetic-subject"}
    assert all(
        len(item["content"]) > 1 and item["expected_segment"] for item in messages
    )
    assert any(item["expected_secondary"] == "family" for item in messages)
    assert any(item["expected_secondary"] == "career" for item in messages)
    assert len({item["expected_segment"] for item in messages}) == 300


def test_corpus_rebuild_matches_committed_fixture_without_a_classifier() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    module = runpy.run_path(str(fixture_dir / "build_history_600_mod.py"))
    expected = json.loads(
        (fixture_dir / "history_600.json").read_text(encoding="utf-8")
    )
    assert module["build_history"]() == expected
    clear_topics = Counter(
        item["expected_topic"] for item in expected if item["clear_assignment"]
    )
    assert set(clear_topics.values()) == {30}

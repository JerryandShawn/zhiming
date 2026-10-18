"""Exact matched-answer statistics; no dependencies on model or scoring services."""

from __future__ import annotations

import math
from typing import Any


def wilson_interval(correct: int, total: int) -> tuple[float, float]:
    if (
        type(correct) is not int
        or type(total) is not int
        or total < 1
        or not 0 <= correct <= total
    ):
        raise ValueError("invalid_accuracy_counts")
    z, p = 1.959963984540054, correct / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = (
        z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    )
    return max(0, center - radius), min(1, center + radius)


def paired_comparison(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> dict[str, Any]:
    first = {row["question_fingerprint"]: row["correct"] for row in left}
    second = {row["question_fingerprint"]: row["correct"] for row in right}
    if (
        len(first) != len(left)
        or len(second) != len(right)
        or first.keys() != second.keys()
        or not first
    ):
        raise ValueError("paired_statistics_require_same_unique_question_set")
    if any(type(value) is not bool for value in [*first.values(), *second.values()]):
        raise ValueError("paired_statistics_require_binary_outcomes")
    differences = [int(second[key]) - int(value) for key, value in first.items()]
    count, mean = len(differences), sum(differences) / len(differences)
    se = (
        math.sqrt(
            sum((value - mean) ** 2 for value in differences) / (count * (count - 1))
        )
        if count > 1
        else None
    )
    losses, gains = differences.count(-1), differences.count(1)
    discordant = losses + gains
    p = min(
        1,
        2
        * sum(math.comb(discordant, value) for value in range(min(losses, gains) + 1))
        / 2**discordant,
    )
    return {
        "questions": count,
        "difference_right_minus_left": mean,
        "paired_standard_error": se,
        "left_only_correct": losses,
        "right_only_correct": gains,
        "mcnemar_exact_two_sided_p": p,
        "limits": (
            "同一命主的题可能相关；逐题配对误差不是对新人物泛化的证明，"
            "多个配置比较未调整多重性。"
        ),
    }


def accuracy_summary(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    if not outcomes:
        raise ValueError("empty_scored_question_set")
    if any(type(row["correct"]) is not bool for row in outcomes) or len(
        {row["question_fingerprint"] for row in outcomes}
    ) != len(outcomes):
        raise ValueError("accuracy_requires_unique_binary_question_outcomes")
    correct, total = sum(row["correct"] for row in outcomes), len(outcomes)
    cases: dict[str, list[bool]] = {}
    for row in outcomes:
        cases.setdefault(row["case_fingerprint"], []).append(row["correct"])
    values = sorted(sum(rows) / len(rows) for rows in cases.values())
    trimmed = sum(values[1:-1]) / (len(values) - 2) if len(values) > 2 else None
    return {
        "questions": total,
        "correct": correct,
        "accuracy": correct / total,
        "wilson_95": wilson_interval(correct, total),
        "case_count": len(cases),
        "trimmed_case_mean": trimmed,
        "trim_method": "remove_one_best_and_one_worst_case_accuracy",
        "trim_method_source": "https://destinylinker.github.io/MingLi-Bench/",
        "leaderboard_shape_8_cases_5_questions": len(cases) == 8
        and all(len(rows) == 5 for rows in cases.values()),
    }

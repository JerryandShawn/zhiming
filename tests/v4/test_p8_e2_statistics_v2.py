"""Hand-calculated matched statistics and same-year control boundary examples."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks.controls_v2 import (
    same_year_placebo,
    shuffle_options,
)
from mingjing_core.adapters.charts.benchmarks.crosscheck_v2 import (
    compare_fields,
    external_chart,
)
from mingjing_core.adapters.charts.benchmarks.scripted_v2 import fixtures
from mingjing_core.adapters.charts.benchmarks.statistics_v2 import (
    accuracy_summary,
    paired_comparison,
    wilson_interval,
)


def outcomes(values: list[bool]) -> list[dict[str, Any]]:
    return [
        {
            "question_fingerprint": str(index),
            "case_fingerprint": "case",
            "correct": value,
        }
        for index, value in enumerate(values)
    ]


def test_wilson_matches_manual_zero_and_half_examples() -> None:
    assert wilson_interval(0, 200) == pytest.approx((0, 0.018845326377266575))
    assert wilson_interval(5, 10) == pytest.approx(
        (0.236593090512564, 0.763406909487436)
    )


def test_paired_difference_and_standard_error_match_hand_calculation() -> None:
    result = paired_comparison(
        outcomes([True, True, False, False]), outcomes([True, False, True, True])
    )
    assert result["difference_right_minus_left"] == 0.25
    assert result["paired_standard_error"] == pytest.approx(math.sqrt(2.75 / 12))
    assert result["left_only_correct"] == 1 and result["right_only_correct"] == 2
    assert result["mcnemar_exact_two_sided_p"] == 1


def test_exact_discordance_and_degenerate_pairing() -> None:
    result = paired_comparison(outcomes([False] * 3), outcomes([True] * 3))
    assert result["difference_right_minus_left"] == 1
    assert result["paired_standard_error"] == 0
    assert result["mcnemar_exact_two_sided_p"] == 0.25
    same = paired_comparison(outcomes([True, False]), outcomes([True, False]))
    assert same["mcnemar_exact_two_sided_p"] == 1
    assert (
        paired_comparison(outcomes([True]), outcomes([False]))["paired_standard_error"]
        is None
    )


def test_trimmed_mean_drops_cases_not_individual_questions_or_trials() -> None:
    rows = []
    for case, correct in enumerate((0, 1, 4, 5)):
        rows += [
            {
                "question_fingerprint": f"{case}-{index}",
                "case_fingerprint": str(case),
                "correct": index < correct,
            }
            for index in range(5)
        ]
    result = accuracy_summary(rows)
    assert result["accuracy"] == result["trimmed_case_mean"] == 0.5
    assert result["leaderboard_shape_8_cases_5_questions"] is False


def test_nonmatching_or_duplicate_questions_cannot_be_reported_as_paired() -> None:
    with pytest.raises(ValueError):
        paired_comparison(outcomes([True]), outcomes([True, False]))
    duplicate = outcomes([True]) * 2
    with pytest.raises(ValueError):
        paired_comparison(duplicate, duplicate)
    with pytest.raises(ValueError):
        paired_comparison([], [])
    with pytest.raises(ValueError):
        accuracy_summary(duplicate)


def test_placebo_keeps_original_questions_keys_and_competition_year_groups() -> None:
    records = [
        replace(
            row,
            competition_year=year,
            id=f"{year}-{row.id}",
            case_id=f"{year}-{row.case_id}",
        )
        for year in (2024, 2025)
        for row in fixtures()
    ]
    shuffled = same_year_placebo(records, 20261018, year_basis="competition_year")
    assert shuffled == same_year_placebo(
        records, 20261018, year_basis="competition_year"
    )
    for original, changed in zip(records, shuffled, strict=True):
        assert original.birth != changed.birth
        assert original.answer == changed.answer and original.text == changed.text
        assert original.case_id == changed.case_id
        donors = [
            row
            for row in records
            if row.source == original.source
            and row.competition_year == original.competition_year
        ]
        assert changed.birth in {row.birth for row in donors}


@pytest.mark.parametrize("basis", ["birth_year", "competition_year"])
def test_placebo_uses_one_donor_for_all_questions_in_a_case(basis: str) -> None:
    records = fixtures()
    records.append(replace(records[0], id="extra-question"))
    changed = same_year_placebo(records, 19, year_basis=basis)
    assert changed[0].birth == changed[-1].birth


def test_impossible_or_missing_year_placebo_matching_fails_closed() -> None:
    records = fixtures()
    for bad in (
        [replace(records[0], competition_year=None)],
        records[:1],
        [records[0], replace(records[1], birth=records[0].birth)],
    ):
        with pytest.raises(ValueError):
            same_year_placebo(bad, 1, year_basis="competition_year")
    with pytest.raises(ValueError):
        same_year_placebo(
            [records[0], replace(records[1], case_id=records[0].case_id)],
            1,
            year_basis="competition_year",
        )


def test_placebo_year_basis_must_be_explicit_and_registered() -> None:
    with pytest.raises(TypeError):
        same_year_placebo(fixtures(), 1)
    with pytest.raises(ValueError):
        same_year_placebo(fixtures(), 1, year_basis="guess")


def test_relabeling_preserves_all_option_text_and_varies_only_with_seeded_trial() -> (
    None
):
    question = fixtures()[0]
    payload, mapping = shuffle_options(question, 44, 0)
    assert set(payload["options"].values()) == {text for _, text in question.options}
    assert "answer" not in payload
    assert sorted(mapping.values()) == list("ABCD")
    assert (payload, mapping) == shuffle_options(question, 44, 0)
    assert (
        len(
            {
                tuple(shuffle_options(question, 44, trial)[1].values())
                for trial in range(20)
            }
        )
        > 1
    )


@pytest.mark.parametrize("correct,total", [(-1, 2), (3, 2), (0, 0), (True, 2)])
def test_invalid_accuracy_counts_are_not_accepted(correct: int, total: int) -> None:
    with pytest.raises(ValueError):
        wilson_interval(correct, total)


def test_external_chart_is_labeled_and_field_crosscheck_does_not_expose_values() -> (
    None
):
    data = {"pillars": {"day": "甲子"}, "hidden": ["丙", "庚", "戊"]}
    bundle = external_chart(data, "bazi", "a" * 64)
    artifact = next(iter(bundle["artifacts"].values()))
    assert artifact["origin"] == "external_chart_not_our_engine_computation"
    assert bundle["calculated_by_our_engine"] is False
    artifact["data"]["pillars"]["day"] = "乙丑"
    assert data["pillars"]["day"] == "甲子"
    comparison = compare_fields(
        data,
        {"day": "甲子", "hidden": ["丙", "戊", "庚"]},
        [("/pillars/day", "/day"), ("/hidden", "/hidden"), ("/missing", "/missing")],
    )
    assert [row["status"] for row in comparison["fields"]] == [
        "equal",
        "different",
        "missing",
    ]
    assert comparison["all_mapped_fields_equal"] is False
    assert "甲子" not in str(comparison)
    assert "our_value" not in comparison["fields"][0]


@pytest.mark.parametrize("index", ["-1", "+1", "01", "1.0", "2"])
def test_invalid_array_indices_are_errors_not_missing_field_matches(index: str) -> None:
    document = {"array": ["synthetic0", "synthetic1"]}
    with pytest.raises(ValueError, match="array_index"):
        compare_fields(document, document, [("/array/" + index, "/array/0")])

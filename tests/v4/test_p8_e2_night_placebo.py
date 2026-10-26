"""One-attempt annual placebo checks use synthetic metadata without inference."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import patch

import pytest

from mingjing_core.adapters.charts.benchmarks import night24_placebo
from mingjing_core.adapters.charts.benchmarks.records import (
    BirthMetadata,
    Question,
    fingerprint,
)


def records(count: int = 3) -> list[Question]:
    return [
        Question(
            id=f"private-id-{number}",
            case_id=f"private-case-{number}",
            text="请问2024年哪项最有可能？PRIVATE_QUESTION",
            options=tuple((letter, "PRIVATE_OPTION_" + letter) for letter in "ABCD"),
            answer="A",
            birth=BirthMetadata(
                1980 + number,
                1,
                2,
                3,
                4,
                "男",
                "PRIVATE_LOCATION",
                "solar",
            ),
            source="synthetic",
            competition_year=2025,
        )
        for number in range(count)
    ]


def test_available_three_cases_changes_every_birth_once_and_preserves_input():
    rows = records()
    original = list(rows)
    with patch.object(
        night24_placebo,
        "same_year_placebo",
        wraps=night24_placebo.same_year_placebo,
    ) as called:
        report = night24_placebo.placebo_preflight(rows)
    called.assert_called_once_with(rows, 20261019, year_basis="question_year")
    assert called.call_args.args[0] is rows
    assert rows == original
    assert report["status"] == "available"
    assert report["actual_call_count"] == 1
    assert report["eligible_questions"] == report["placebo_questions"] == 3
    assert report["changed_births_count"] == 3
    assert report["groups"] == [
        {
            "source": "synthetic",
            "target_year": 2024,
            "case_count": 3,
            "distinct_birth_count": 3,
            "structurally_unmatchable": False,
        }
    ]
    assert report == night24_placebo.placebo_preflight(rows)


def test_multi_year_case_is_not_split_or_retried():
    rows = records()
    rows.append(replace(rows[0], id="private-next", text="请问2023年会有什么？"))
    with patch.object(
        night24_placebo,
        "same_year_placebo",
        wraps=night24_placebo.same_year_placebo,
    ) as called:
        report = night24_placebo.placebo_preflight(rows)
    assert called.call_count == 1
    assert report["status"] == "unavailable"
    assert report["error_code"] == (
        "placebo_case_spans_question_years_cannot_preserve_one_donor"
    )
    assert report["multi_year_case_count"] == 1
    assert report["multi_year_cases"] == [
        {
            "source": "synthetic",
            "case_identity_sha256": fingerprint(["synthetic", rows[0].case_id]),
            "target_years": [2023, 2024],
        }
    ]
    assert report["singleton_group_count"] == 1
    assert report["group_count"] == 2
    assert report["changed_births_count"] == 0


def test_complete_fourteen_batch_reports_all_blockers_after_first_error():
    rows = records(9)
    years = list(range(2010, 2020)) + [2020, 2021, 2022, 2022]
    cases = [number // 2 for number in range(10)] + [5, 6, 7, 8]
    batch = [
        replace(
            rows[case],
            id=f"private-question-{number}",
            text=f"请问{year}年会有什么？",
        )
        for number, (case, year) in enumerate(zip(cases, years, strict=True))
    ]
    with patch.object(
        night24_placebo,
        "same_year_placebo",
        wraps=night24_placebo.same_year_placebo,
    ) as called:
        report = night24_placebo.placebo_preflight(batch)
    called.assert_called_once_with(batch, 20261019, year_basis="question_year")
    assert report["eligible_questions"] == 14
    assert report["multi_year_case_count"] == 5
    assert report["group_count"] == 13
    assert report["singleton_group_count"] == 12
    assert report["status"] == "unavailable"
    assert report["error_code"] == (
        "placebo_case_spans_question_years_cannot_preserve_one_donor"
    )


@pytest.mark.parametrize("separate", ["source", "year"])
def test_singletons_never_borrow_across_source_or_question_year(separate):
    rows = records(2)
    rows[1] = (
        replace(rows[1], source="another_synthetic_source")
        if separate == "source"
        else replace(rows[1], text="请问2023年哪项最可能？")
    )
    report = night24_placebo.placebo_preflight(rows)
    assert report["status"] == "unavailable"
    assert report["singleton_group_count"] == 2
    assert all(row["structurally_unmatchable"] for row in report["groups"])
    assert report["error_code"] == (
        "same_year_distinct_birth_placebo_matching_unavailable"
    )
    assert report["retries"] == 0
    assert report["complete_batch_only"] is True
    assert report["cross_year_fallback"] is False
    assert report["cross_source_fallback"] is False


def test_same_birth_cases_are_reported_as_structurally_unmatchable():
    rows = records(2)
    rows[1] = replace(rows[1], birth=rows[0].birth)
    report = night24_placebo.placebo_preflight(rows)
    assert report["groups"][0]["case_count"] == 2
    assert report["groups"][0]["distinct_birth_count"] == 1
    assert report["groups"][0]["structurally_unmatchable"] is True
    assert report["status"] == "unavailable"


def test_case_birth_conflict_uses_safe_error_code():
    rows = records(2)
    rows[1] = replace(rows[1], case_id=rows[0].case_id)
    report = night24_placebo.placebo_preflight(rows)
    assert report["error_code"] == "placebo_case_birth_conflict"


def test_ambiguous_year_is_not_replaced_with_contest_or_birth_year():
    rows = [replace(records(1)[0], text="请问今年会怎样？")]
    report = night24_placebo.placebo_preflight(rows)
    assert report["status"] == "unavailable"
    assert report["eligible_questions"] == 0
    assert report["error_code"] == "placebo_explicit_question_year_missing"
    assert report["group_count"] == 0


def test_empty_batch_still_has_one_declared_call():
    with patch.object(
        night24_placebo,
        "same_year_placebo",
        wraps=night24_placebo.same_year_placebo,
    ) as called:
        report = night24_placebo.placebo_preflight([])
    called.assert_called_once_with([], 20261019, year_basis="question_year")
    assert report["status"] == "no_eligible_questions"
    assert report["eligible_questions"] == report["placebo_questions"] == 0
    assert report["actual_call_count"] == 1


@pytest.mark.parametrize(
    "error", [ValueError("PRIVATE_ERROR_BIRTH"), RuntimeError("PRIVATE_ERROR_TEXT")]
)
def test_unknown_errors_are_not_echoed_or_raised(error):
    with patch.object(night24_placebo, "same_year_placebo", side_effect=error):
        report = night24_placebo.placebo_preflight(records())
    assert report["status"] == "unavailable"
    assert report["error_code"] == "e2_placebo_preflight_failed"
    assert "PRIVATE_ERROR" not in json.dumps(report)


@pytest.mark.parametrize("multiple_years", [False, True])
def test_report_never_exposes_question_ids_text_birth_or_birth_hash(multiple_years):
    rows = records()
    if multiple_years:
        rows.append(replace(rows[0], id="private-next", text="请问2023年会有什么？"))
    report = night24_placebo.placebo_preflight(rows)
    encoded = json.dumps(report, ensure_ascii=False)
    for row in rows:
        for protected in (
            row.id,
            row.case_id,
            row.text,
            row.birth.location,
            fingerprint(row.birth.public_input()),
            *dict(row.options).values(),
        ):
            assert protected not in encoded
    assert '"birth"' not in encoded
    assert '"answer"' not in encoded

"""Brain 23 exclusions protect denominators and never infer a missing source year."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks.controls_v2 import same_year_placebo
from mingjing_core.adapters.charts.benchmarks.eligibility_v2 import (
    YearReview,
    question_year,
    select_questions,
)
from mingjing_core.adapters.charts.benchmarks.loaders import load_baziqa
from mingjing_core.adapters.charts.benchmarks.loaders_v2 import load_corpus_v2
from mingjing_core.adapters.charts.benchmarks.protocol_v2 import run_configuration_v2
from mingjing_core.adapters.charts.benchmarks.scripted_v2 import fixtures


@pytest.mark.parametrize(
    "text,year,reason",
    [
        ("请问2025年的事业如何？", 2025, "explicit_target_clause"),
        (
            "1988年出生，已知2010年毕业；请问2025年事业如何？",
            2025,
            "explicit_target_clause",
        ),
        ("1988年出生请问2025年事业如何？", 2025, "explicit_target_clause"),
        ("曾于2018年转行；2025年最可能发生什么？", 2025, "explicit_target_clause"),
        ("2025年事业如何，2025年财运如何？", 2025, "explicit_target_clause"),
        ("请问今年事业如何？", None, "ambiguous_relative_target_year"),
        ("请问2024年和2025年哪年更好？", None, "ambiguous_multiple_target_years"),
        ("2000年出生，请问事业如何？", None, "explicit_year_target_unresolved"),
        ("曾于2020年毕业，请问事业如何？", None, "explicit_year_target_unresolved"),
        ("请问事业如何？", None, "no_explicit_target_year"),
        ("明年事业如何？", None, "ambiguous_relative_target_year"),
        ("请问二〇二五年的事业如何？", None, "no_explicit_target_year"),
        ("2025年事业如何，明年如何？", None, "ambiguous_relative_target_year"),
    ],
)
def test_only_explicit_target_clause_year_is_accepted(
    text: str, year: int | None, reason: str
) -> None:
    record = replace(fixtures()[0], text=text, competition_year=2099)
    result = question_year(record)
    assert result.year == year and result.reason == reason
    for start, end in result.evidence_spans:
        assert str(year) in record.text[start:end]


def test_year_review_is_bound_to_question_and_exact_target_token() -> None:
    record = replace(fixtures()[0], text="背景2010年；2024年、2025年运势比较。")
    start = record.text.index("2025年")
    review = YearReview(record.scoring_fingerprint(), 2025, start, start + 5)
    assert question_year(record).eligible is False
    assert question_year(record, review).year == 2025
    with pytest.raises(ValueError, match="fingerprint_mismatch"):
        question_year(replace(record, text=record.text + "修订"), review)
    with pytest.raises(ValueError, match="explicit_question_year"):
        question_year(record, replace(review, year=2026))
    with pytest.raises(ValueError, match="span"):
        question_year(record, replace(review, start=-1))


def test_birth_clause_cannot_be_manual_target_year_or_metadata_fallback() -> None:
    record = replace(
        fixtures()[0], text="1990年出生，问今年如何？", competition_year=2025
    )
    review = YearReview(record.scoring_fingerprint(), 1990, 0, 5)
    with pytest.raises(ValueError, match="birth_clause"):
        question_year(record, review)
    assert question_year(record).year is None
    assert question_year(replace(record, competition_year=2024)).year is None


def test_review_can_locate_target_year_alongside_birth_year_in_one_clause() -> None:
    record = replace(fixtures()[0], text="1990年1月2日出生、2024年和2025年的事业比较。")
    start = record.text.index("2025年")
    review = YearReview(record.scoring_fingerprint(), 2025, start, start + 5)
    assert question_year(record, review).year == 2025
    with pytest.raises(ValueError, match="birth_clause"):
        question_year(record, YearReview(record.scoring_fingerprint(), 1990, 0, 5))


def test_audit_contains_only_hashes_counts_and_offsets_without_source_text() -> None:
    valid, invalid = fixtures()[0], replace(fixtures()[1], text="无明确年份的合成题")
    records, report = select_questions([valid, invalid])
    assert records == [valid]
    assert report["source_questions"] == 2 and report["excluded_questions"] == 1
    assert report["metadata_year_fallback"] is False
    rendered = json.dumps(report, ensure_ascii=False)
    assert valid.text not in rendered and invalid.text not in rendered
    assert valid.case_id not in rendered and valid.birth.location not in rendered
    with pytest.raises(ValueError, match="unknown_questions"):
        select_questions(
            [valid], reviews={"unknown": YearReview("unknown", 2025, 0, 5)}
        )


def test_all_excluded_protocol_does_not_call_any_provider_or_report_fake_score() -> (
    None
):
    def forbidden(_: Any) -> Any:
        raise AssertionError("excluded question reached a provider")

    result = run_configuration_v2(
        [replace(fixtures()[0], text="今年如何？")],
        "C4a",
        forbidden,
        forbidden,
        forbidden,
        seed=1,
    )
    assert result["status"] == "all_questions_excluded"
    assert result["protocol_stage_calls"] == result["model_requests"] == 0
    assert result["summary"] is None and result["outcomes"] == []


def test_protocol_filters_before_requests_and_supplies_explicit_target_year() -> None:
    seen = []

    def answer(request: Any) -> str:
        seen.append(request.question)
        assert request.question["target_year"] == 2025
        assert request.question["year_basis"] == "question_explicit_target_year"
        return "A"

    result = run_configuration_v2(
        [fixtures()[0], replace(fixtures()[1], text="去年如何？")],
        "C0",
        lambda _: {},
        lambda _: {},
        answer,
        seed=1,
    )
    assert len(seen) == result["protocol_stage_calls"] == 1
    assert result["summary"]["questions"] == 1
    assert result["question_eligibility"]["excluded_questions"] == 1


def test_question_year_placebo_keeps_case_donor_and_never_uses_contest_metadata() -> (
    None
):
    records = [
        replace(row, competition_year=2020 + i) for i, row in enumerate(fixtures())
    ]
    records += [replace(records[0], id="same-case-next-question")]
    result = same_year_placebo(records, 3, year_basis="question_year")
    assert result[0].birth == result[-1].birth
    assert all(
        left.birth != right.birth for left, right in zip(records, result, strict=True)
    )
    with pytest.raises(ValueError, match="explicit_question_year_missing"):
        same_year_placebo(
            [replace(row, text="今年如何？") for row in records],
            3,
            year_basis="question_year",
        )


def test_question_year_placebo_does_not_change_one_person_chart_between_years() -> None:
    records = fixtures() + [
        replace(fixtures()[0], id="another-year", text="2024年事业如何？")
    ]
    with pytest.raises(ValueError, match="cannot_preserve_one_donor"):
        same_year_placebo(records, 3, year_basis="question_year")


def _baziqa(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"contest_id": "synthetic", "current_year": "2025"},
        {
            "person_id": "synthetic",
            "profile": {
                "birth": {"year": 1990, "month": 1, "day": 1, "hour": 8},
                "gender": "male",
            },
            "questions": questions,
        },
    ]


def _item(ident: str, **changes: Any) -> dict[str, Any]:
    return {
        "question_id": ident,
        "question": "请问2025年事业如何？",
        "options": ["A. 一", "B 二", "C 三", "D 四"],
        "answer": "A",
    } | changes


def _write(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_missing_label_excludes_one_question_instead_of_whole_baziqa_file(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path / "synthetic.json",
        _baziqa(
            [
                _item("valid"),
                _item("bad", options=["A 一", "B 二", "三没有标签", "D 四"]),
                _item("ambiguous", question="今年事业如何？"),
            ]
        ),
    )
    result = load_corpus_v2(path, "baziqa")
    assert len(result.records) == 1 and result.records[0].birth.minute is None
    assert (
        result.report["source_questions"] == 3
        and result.report["schema_valid_questions"] == 2
    )
    assert result.report["excluded_reasons"] == {
        "missing_or_invalid_option_labels": 1,
        "ambiguous_relative_target_year": 1,
    }
    with pytest.raises(ValueError, match="unrecognized_source_option"):
        load_baziqa(path)  # Historical v1 contract remains strict and unchanged.


@pytest.mark.parametrize(
    "options", [["A 一", "B 二", "D 四"], ["A 一", "A 二", "C 三", "D 四"]]
)
def test_missing_or_duplicate_labels_are_not_invented(
    tmp_path: Path, options: list[str]
) -> None:
    path = _write(
        tmp_path / "synthetic.json",
        _baziqa([_item("good"), _item("bad", options=options)]),
    )
    result = load_corpus_v2(path, "baziqa")
    assert len(result.records) == 1
    assert result.report["excluded_reasons"] == {"missing_or_invalid_option_labels": 1}


def test_duplicate_ids_exclude_all_copies_and_missing_answer_is_separate(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path / "synthetic.json",
        _baziqa([_item("repeat"), _item("repeat"), _item("bad", answer="E")]),
    )
    result = load_corpus_v2(path, "baziqa")
    assert result.records == ()
    assert result.report["excluded_reasons"] == {
        "missing_or_invalid_answer_label": 1,
        "duplicate_question_identity": 2,
    }


def test_competition_year_filters_subset_but_does_not_decide_target_year(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path / "synthetic.json",
        _baziqa([_item("valid", question="请问2010年事业如何？")]),
    )
    included = load_corpus_v2(path, "baziqa", competition_year=2025)
    assert question_year(included.records[0]).year == 2010
    excluded = load_corpus_v2(path, "baziqa", competition_year=2024)
    assert excluded.records == ()
    assert excluded.report["excluded_reasons"] == {
        "outside_requested_contest_subset": 1
    }


def test_inconsistent_case_births_are_excluded_together(tmp_path: Path) -> None:
    data = _baziqa([_item("first")])
    other = json.loads(json.dumps(data[1]))
    other["profile"]["birth"]["year"] = 1991
    other["questions"] = [_item("second")]
    data.append(other)
    result = load_corpus_v2(_write(tmp_path / "synthetic.json", data), "baziqa")
    assert result.records == ()
    assert result.report["source_cases"] == 1
    assert result.report["excluded_reasons"] == {
        "inconsistent_birth_for_source_case": 2
    }


def test_pinned_local_cache_count_evidence_preserves_real_denominators() -> None:
    evidence = (
        Path(__file__).resolve().parents[2]
        / "docs/v4/evidence/P8/e2-brain23-adjudication-2026-10-18.json"
    )
    report = json.loads(evidence.read_text(encoding="utf-8"))
    assert report["real_model_requests"] == report["new_downloads"] == 0
    mingli, baziqa = report["sources"]
    assert (
        mingli["source_questions"],
        mingli["schema_valid_questions"],
        mingli["included_questions"],
    ) == (160, 160, 22)
    assert (
        baziqa["source_questions"],
        baziqa["schema_valid_questions"],
        baziqa["included_questions"],
    ) == (200, 199, 26)
    by_file = {row["file"]: row for row in baziqa["files"]}
    year2021 = by_file["contest8_2021.json"]
    assert year2021["source_questions"] == 40 and year2021["source_cases"] == 9
    assert year2021["included_questions"] == 8 and year2021["included_cases"] == 5
    year2023 = by_file["contest8_2023.json"]
    assert year2023["schema_valid_questions"] == 39
    assert year2023["excluded_reasons"]["missing_or_invalid_option_labels"] == 1
    assert (
        year2023["sha256"]
        == "920afd8acbc1e17c360dc940c79833b096893a7483420b832f9929a1d8f0eed4"
    )
    for source in report["sources"]:
        for row in source["files"]:
            assert (
                row["source_questions"]
                == row["included_questions"] + row["excluded_questions"]
            )
            assert row["excluded_questions"] == sum(row["excluded_reasons"].values())
            assert len(row["excluded_audit"]) == row["excluded_questions"]
            assert (
                row["scored"] is False and row["source_content_redistributed"] is False
            )

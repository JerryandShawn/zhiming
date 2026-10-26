"""E2 offline boundary tests use synthetic bodies and no professional dataset text."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks.engine import P8Engine
from mingjing_core.adapters.charts.benchmarks.experiment import (
    CONFIGURATIONS,
    InferenceRequest,
    parse_selection,
    placebo_births,
    run_configuration,
)
from mingjing_core.adapters.charts.benchmarks.loaders import (
    inspect_corpus,
    load_baziqa,
    load_mingli,
)
from mingjing_core.adapters.charts.benchmarks.records import (
    BirthMetadata,
    CalculationInputs,
    fingerprint,
)
from mingjing_core.adapters.charts.benchmarks.scripted import synthetic_questions


def _write(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _mingli() -> dict[str, Any]:
    return {
        "questions": [
            {
                "id": "synthetic-source-1",
                "case_id": "synthetic-case-1",
                "question": "合成规范化测试？",
                "options": [
                    {"letter": letter, "text": "合成选项" + letter} for letter in "ABCD"
                ],
                "answer": "C",
                "birth_info": {
                    "year": 2000,
                    "month": 2,
                    "day": 29,
                    "hour": 8,
                    "gender": "男",
                    "calendar_type": "solar",
                },
                "has_answer": True,
                "question_number": 41,
            }
        ]
    }


def test_mingli_normalization_does_not_invent_missing_minute_or_location(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path / "synthetic.json", _mingli())
    question = load_mingli(path)[0]
    assert question.answer == "C"
    assert question.competition_year == 2023
    assert question.birth.minute is None
    assert question.birth.location is None
    assert question.birth.approximate is None
    summary = inspect_corpus(path, "mingli")
    assert summary["missing_birth_fields"]["minute"] == 1
    assert summary["scored"] is False
    assert "question" not in summary and "birth" not in summary


def test_baziqa_header_and_string_options_are_normalized(tmp_path: Path) -> None:
    data = [
        {"contest_id": "synthetic", "current_year": "2025"},
        {
            "person_id": "synthetic",
            "profile": {
                "birth": {
                    "year": 2001,
                    "month": 4,
                    "day": 3,
                    "hour": 8,
                    "minute": 0,
                    "approximate": True,
                },
                "gender": "female",
            },
            "questions": [
                {
                    "question_id": "Q1",
                    "question": "合成测试？",
                    "options": ["A. 一", "B 二", "C、三", "D：四"],
                    "answer": "D",
                }
            ],
        },
    ]
    result = load_baziqa(_write(tmp_path / "contest-synthetic.json", data))
    assert result[0].competition_year == 2025
    assert result[0].birth.gender == "女" and result[0].birth.approximate is True
    assert result[0].options[-1] == ("D", "四")


def test_official_lowercase_and_separator_free_label_variants(tmp_path: Path) -> None:
    data = _mingli()
    data["questions"][0]["options"] = ["a. 一", "B二", "c、三", "D：四"]
    assert load_mingli(_write(tmp_path / "synthetic.json", data))[0].options == (
        ("A", "一"),
        ("B", "二"),
        ("C", "三"),
        ("D", "四"),
    )


def test_missing_option_label_blocks_file_without_inferred_answer(
    tmp_path: Path,
) -> None:
    data = _mingli()
    data["questions"][0]["options"] = ["A 一", "B 二", "缺失标签", "D 四"]
    path = _write(tmp_path / "missing-label.json", data)
    with pytest.raises(ValueError, match="unrecognized_source_option"):
        load_mingli(path)
    summary = inspect_corpus(path, "mingli")
    assert summary["parse_status"] == "blocked_source_schema_requires_review"
    assert summary["questions"] == 0 and summary["scored"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"has_answer": False},
        {"answer": "E"},
        {"answer": "A,C"},
        {"options": [{"letter": "A", "text": "只有一个"}]},
    ],
)
def test_malformed_source_cannot_silently_change_denominator(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    data = _mingli()
    data["questions"][0].update(change)
    with pytest.raises(ValueError):
        load_mingli(_write(tmp_path / "synthetic.json", data))


def test_duplicate_questions_and_inconsistent_case_births_are_rejected(
    tmp_path: Path,
) -> None:
    data = _mingli()
    data["questions"] *= 2
    with pytest.raises(ValueError, match="duplicate"):
        load_mingli(_write(tmp_path / "duplicate.json", data))
    other = json.loads(json.dumps(data["questions"][0]))
    other["id"] = "different"
    other["birth_info"]["year"] = 2004
    data["questions"][1] = other
    with pytest.raises(ValueError, match="inconsistent_birth"):
        load_mingli(_write(tmp_path / "inconsistent.json", data))


@pytest.mark.parametrize(
    "field,value", [("year", True), ("hour", 24), ("minute", -1), ("day", 30)]
)
def test_invalid_birth_fields_are_rejected(
    tmp_path: Path, field: str, value: Any
) -> None:
    data = _mingli()
    data["questions"][0]["birth_info"][field] = value
    with pytest.raises(ValueError):
        load_mingli(_write(tmp_path / "invalid-birth.json", data))


def test_placebo_is_seeded_case_consistent_derangement_without_moving_answers() -> None:
    questions = synthetic_questions()
    questions += [replace(questions[0], id="synthetic-second-question")]
    first = placebo_births(questions, 42)
    assert first == placebo_births(questions, 42)
    for original, control in zip(questions, first, strict=True):
        assert original.birth != control.birth
        assert original.answer == control.answer and original.text == control.text
        assert original.id == control.id
    assert first[0].birth == first[-1].birth
    with pytest.raises(ValueError):
        placebo_births(questions[:1], 42)


def test_placebo_refuses_conflicting_births_inside_one_case() -> None:
    questions = synthetic_questions()
    questions.append(replace(questions[0], id="conflicting", birth=questions[1].birth))
    with pytest.raises(ValueError, match="inconsistent_birth"):
        placebo_births(questions, 42)


def test_answerer_cannot_mutate_cached_calculation_evidence() -> None:
    chart = {"nested": {"original": True}}
    expected = fingerprint(chart)

    def answerer(request: InferenceRequest) -> str:
        request.chart["nested"]["original"] = False
        request.question["options"]["A"] = "改写选项"
        return "A"

    result = run_configuration(
        synthetic_questions()[:1],
        "direct",
        lambda _: chart,
        answerer,
        control="original",
        execution_kind="scripted_test",
    )
    assert chart == {"nested": {"original": True}}
    assert result["outcomes"][0]["chart_fingerprint"] == expected
    assert result["correct"] == 1


@pytest.mark.parametrize(
    "text,expected",
    [
        ("A", "A"),
        ('{"answer":"D"}', "D"),
        ("A or B", None),
        ("答案 A", None),
        ('{"answer":"B", "extra":1}', None),
        ('["A"]', None),
        ("", None),
        ("AB", None),
    ],
)
def test_scoring_rejects_ambiguous_or_explanatory_outputs(
    text: str, expected: str | None
) -> None:
    assert parse_selection(text) == expected


@pytest.mark.parametrize("configuration", CONFIGURATIONS)
def test_protocol_plans_hide_key_and_exercise_deep_specialist_stage(
    configuration: str,
) -> None:
    requests: list[InferenceRequest] = []

    def answerer(request: InferenceRequest) -> str:
        requests.append(request)
        assert "answer" not in request.question and "source" not in request.question
        assert request.chart == {"injected": True}
        return "专科证据" if request.stage == "specialist" else "A"

    result = run_configuration(
        synthetic_questions()[:1],
        configuration,
        lambda _: {"injected": True},
        answerer,
        control="original",
        execution_kind="scripted_test",
    )
    assert result["correct"] == 1 and result["invalid"] == 0
    assert result["actual_v4_agent_runtime"] is False
    assert len(requests) == (2 if configuration == "deep" else 1)
    if configuration == "deep":
        assert requests[-1].specialist_output == "专科证据"


def test_missing_geography_is_not_guessed_and_never_calls_engine() -> None:
    engine = P8Engine("not-an-interpreter", {}, "2026-10-18")
    with pytest.raises(ValueError, match="missing_verified"):
        engine(synthetic_questions()[0].birth)


@pytest.mark.parametrize(
    "inputs",
    [
        (float("nan"), 8, "source", True),
        (120, 99, "source", True),
        (True, 8, "source", True),
        (120, 8, "", True),
        (120, 8, "source", False),
    ],
)
def test_calculation_overlay_requires_finite_provenanced_explicit_inputs(
    inputs: tuple[Any, ...],
) -> None:
    with pytest.raises(ValueError):
        CalculationInputs(*inputs)


def test_non_solar_birth_keeps_calendar_metadata() -> None:
    birth = BirthMetadata(2000, 12, 30, None, None, None, None, "lunar")
    assert birth.calendar == "lunar" and birth.hour is None

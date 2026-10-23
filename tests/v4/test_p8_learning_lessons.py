"""Static course drafts must resolve actual synthetic evidence without new calls."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mingjing_core.adapters.charts.benchmarks.handoff_offline import (
    denied,
    offline_runtime,
)
from mingjing_core.skills.learning import learning_outline

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "mingjing_core/knowledge/p8_learning_lessons"
SCHEMA = ROOT / "docs/v4/contracts/learning_lessons.schema.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _file(root: Path, value: str) -> Path:
    if "\\" in value or ".." in value.split("/"):
        raise ValueError("unsafe_course_path")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("unsafe_course_path")
    return path


def _pointer(value: object, path: str) -> object:
    if path == "":
        return value
    if not path.startswith("/"):
        raise ValueError("course_pointer_invalid")
    for raw in path[1:].split("/"):
        if re.search(r"~(?![01])", raw):
            raise ValueError("course_pointer_invalid")
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            if int(key) >= len(value):
                raise ValueError("course_pointer_invalid")
            value = value[int(key)]
        else:
            raise ValueError("course_pointer_invalid")
    return value


def _alias(chart: dict, category: str, alias: str) -> dict:
    found = [row for row in chart["aliases"][category] if row["alias"] == alias]
    if len(found) != 1:
        raise ValueError("course_alias_missing")
    return found[0]


def _follow(chart: dict, ref: dict) -> object:
    documents = [
        row for row in chart["documents"] if row["document_id"] == ref["document_id"]
    ]
    if len(documents) != 1:
        raise ValueError("course_document_missing")
    return _pointer(documents[0]["payload"], ref["path"])


def _binding(evidence: dict, charts: dict) -> object:
    chart = charts[evidence["case_id"]]
    alias = _alias(chart, "c", evidence["c_alias"])
    if alias["scope"] != chart["scope"]:
        raise ValueError("course_scope_mismatch")
    if evidence["role"] == "primary":
        if alias["ref"] not in chart["view"]["primary"]:
            raise ValueError("course_primary_required")
    elif evidence["role"] == "basis":
        if not re.fullmatch(
            r"/time_basis/items/[0-9]+/source_variants/[0-9]+/coordinate_datetime",
            alias["ref"]["path"],
        ):
            raise ValueError("course_basis_required")
    elif evidence["role"] != "rule_input" or not evidence["r_aliases"]:
        raise ValueError("course_rule_required")
    value = _pointer(_follow(chart, alias["ref"]), evidence["relative_path"])
    if _canonical(value) != _canonical(evidence["expected"]):
        raise ValueError("course_observation_changed")
    for key in evidence["r_aliases"]:
        rule_alias = _alias(chart, "r", key)
        rule = _follow(chart, rule_alias["ref"])
        if rule_alias["scope"] != chart["scope"] or rule.get("met") is not True:
            raise ValueError("course_rule_invalid")
        if evidence["c_alias"] not in rule_alias["evidence_aliases"]:
            raise ValueError("course_rule_input_mismatch")
        if rule_alias["rule_id"] != rule.get("rule_id"):
            raise ValueError("course_rule_identity_mismatch")
    return value


def _quiz(quiz: dict, evidence: dict, charts: dict, source_ids: set[str]) -> None:
    options = {row["option_id"]: row for row in quiz["options"]}
    if len(options) != 3 or quiz["correct_option_id"] not in options:
        raise ValueError("course_options_invalid")
    expected = quiz["basis"]["expected"]
    correct = options[quiz["correct_option_id"]]
    if _canonical(correct["value"]) != _canonical(expected):
        raise ValueError("course_answer_changed")
    if len({_canonical(row["value"]) for row in options.values()}) != 3:
        raise ValueError("course_options_ambiguous")
    basis = quiz["basis"]
    if basis["kind"] == "concept":
        if not set(basis["source_ids"]) <= source_ids:
            raise ValueError("course_concept_source_missing")
        if re.search(r"〔[cr][1-9][0-9]*〕", quiz["explanation"]):
            raise ValueError("course_concept_fake_alias")
        return
    observed = evidence[basis["evidence_id"]]
    if _canonical(_binding(observed, charts)) != _canonical(expected):
        raise ValueError("course_answer_evidence_mismatch")
    if (basis["kind"] == "matched_rule") != bool(observed["r_aliases"]):
        raise ValueError("course_quiz_rule_kind_mismatch")


@pytest.fixture(scope="module")
def course():
    with (
        offline_runtime(),
        patch.object(subprocess, "run", denied),
        patch.object(subprocess, "Popen", denied),
    ):
        catalog = _read(DIRECTORY / "curriculum_v1.json")
        schema = _read(SCHEMA)
        Draft202012Validator.check_schema(schema)
        cases = {row["case_id"]: row for row in catalog["cases"]}
        charts, learning = {}, {}
        for identity, row in cases.items():
            charts[identity] = _read(_file(ROOT, row["chart_path"]))
            learning[identity] = _read(_file(ROOT, row["learning_path"]))
        yield {
            "catalog": catalog,
            "validator": Draft202012Validator(schema, format_checker=FormatChecker()),
            "cases": cases,
            "charts": charts,
            "learning": learning,
            "evidence": {row["evidence_id"]: row for row in catalog["evidence"]},
            "sources": _read(_file(ROOT, catalog["source_registry"]["path"])),
        }


def test_curriculum_schema_and_twenty_distinct_lessons(course):
    catalog = course["catalog"]
    course["validator"].validate(catalog)
    assert len(catalog["lessons"]) == 20
    assert [row["order"] for row in catalog["lessons"]] == list(range(1, 21))
    assert len({row["title"] for row in catalog["lessons"]}) == 20
    assert len(course["evidence"]) == len(catalog["evidence"])


@pytest.mark.parametrize("case_id", ["ayuan-bazi", "ayuan-ziwei", "ayuan-astro"])
def test_pinned_actual_charts_and_learning_replay(course, case_id):
    case = course["cases"][case_id]
    for prefix in ("chart", "learning"):
        path = _file(ROOT, case[prefix + "_path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case[prefix + "_sha256"]
    assert case["scope"] == course["charts"][case_id]["scope"]
    assert case["scope"] == course["learning"][case_id]["scope"]
    assert learning_outline(course["charts"][case_id]) == course["learning"][case_id]
    assert case["learning_point_ids"] == [
        row["point_id"] for row in course["learning"][case_id]["points"]
    ]


def test_sources_registry_pinned_and_local_paths_exist(course):
    source = course["catalog"]["source_registry"]
    assert (
        hashlib.sha256(_file(ROOT, source["path"]).read_bytes()).hexdigest()
        == source["sha256"]
    )
    assert course["sources"]["version"] == source["version"]
    for row in course["sources"]["sources"]:
        if row["path"]:
            assert _file(ROOT, row["path"]).is_file()


@pytest.mark.parametrize("order", range(1, 21))
def test_individual_lesson_shape_content_and_provenance(course, order):
    entry = course["catalog"]["lessons"][order - 1]
    lesson = _read(_file(DIRECTORY, entry["path"]))
    course["validator"].validate(lesson)
    for name in ("lesson_id", "order", "title", "level", "status"):
        assert entry[name] == lesson[name]
    assert lesson["prerequisite_ids"] == (
        [] if order == 1 else [f"lesson-{order - 1:02}"]
    )
    source_ids = {row["source_id"] for row in course["sources"]["sources"]}
    assert set(lesson["source_ids"]) <= source_ids
    assert all(
        set(row["source_ids"]) <= source_ids for row in lesson["school_differences"]
    )
    for example in lesson["worked_examples"]:
        for key in example["evidence_ids"]:
            evidence = course["evidence"][key]
            assert evidence["case_id"] == example["case_id"]
            _binding(evidence, course["charts"])
        points = course["cases"][example["case_id"]]["learning_point_ids"]
        assert set(example["learning_point_ids"]) <= set(points)
    assert all(len(text) >= 35 for text in lesson["paragraphs"])


@pytest.mark.parametrize("order,number", [(a, b) for a in range(1, 21) for b in (1, 2)])
def test_each_quiz_answer_has_actual_evidence_or_concept_source(course, order, number):
    lesson = _read(DIRECTORY / "lessons" / f"lesson-{order:02}.json")
    quiz = lesson["quiz"][number - 1]
    _quiz(quiz, course["evidence"], course["charts"], set(lesson["source_ids"]))


def test_no_bulk_repeated_paragraphs_questions_or_single_answer_position(course):
    lessons = [_read(DIRECTORY / row["path"]) for row in course["catalog"]["lessons"]]
    paragraphs = [text for row in lessons for text in row["paragraphs"]]
    questions = [quiz["question"] for row in lessons for quiz in row["quiz"]]
    answers = [quiz["correct_option_id"] for row in lessons for quiz in row["quiz"]]
    assert len(paragraphs) == len(set(paragraphs))
    assert len(questions) == len(set(questions)) == 40
    assert all(answers.count(key) >= 10 for key in "abc")


@pytest.mark.parametrize(
    "field,value", [("c_alias", "c2"), ("relative_path", "/missing")]
)
def test_diagnostic_or_missing_pointer_is_rejected(course, field, value):
    evidence = deepcopy(course["evidence"]["master"])
    evidence[field] = value
    with pytest.raises(ValueError):
        _binding(evidence, course["charts"])


def test_cross_case_and_wrong_expected_value_are_rejected(course):
    for field, value in (("case_id", "ayuan-ziwei"), ("expected", "甲")):
        evidence = deepcopy(course["evidence"]["master"])
        evidence[field] = value
        with pytest.raises(ValueError):
            _binding(evidence, course["charts"])


@pytest.mark.parametrize("aliases", [["r999"], ["r7"]])
def test_missing_rule_or_wrong_rule_input_is_rejected(course, aliases):
    evidence = deepcopy(course["evidence"]["hurting_clear"])
    evidence["r_aliases"] = aliases
    with pytest.raises(ValueError):
        _binding(evidence, course["charts"])


@pytest.mark.parametrize("path", ["/-1", "/01", "/١", "/~2", "/3", "0"])
def test_pointer_boundaries_refuse_noncanonical_indices(path):
    with pytest.raises(ValueError):
        _pointer([1, 2], path)


def test_answer_wrong_type_or_fake_concept_alias_is_rejected(course):
    lesson = _read(DIRECTORY / "lessons/lesson-11.json")
    question = deepcopy(lesson["quiz"][0])
    question["options"][0]["value"] = 1
    with pytest.raises(ValueError, match="course_answer_changed"):
        _quiz(question, course["evidence"], course["charts"], set(lesson["source_ids"]))
    concept = deepcopy(lesson["quiz"][1])
    concept["explanation"] += "〔r999〕"
    with pytest.raises(ValueError, match="course_concept_fake_alias"):
        _quiz(concept, course["evidence"], course["charts"], set(lesson["source_ids"]))


@pytest.mark.parametrize(
    "path", ["../AGENTS.md", "C:/secret", "a/../../secret", "a\\b"]
)
def test_source_path_boundaries(path):
    with pytest.raises(ValueError, match="unsafe_course_path"):
        _file(ROOT, path)

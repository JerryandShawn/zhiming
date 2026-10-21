"""Displayed course citations must belong to their exact synthetic evidence case."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.tool_evidence import pointer

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "mingjing_core/knowledge/p8_learning_lessons"
CITATION = re.compile(r"〔([cr][^〕]*)〕")
ALIAS = re.compile(r"[cr][1-9][0-9]*")


def read_relative(root: Path, relative: str) -> dict:
    path = (root / relative).resolve()
    assert path.is_relative_to(root.resolve()) and path.is_file()
    return json.loads(path.read_bytes())


@pytest.fixture(scope="module")
def study() -> dict:
    catalog = read_relative(DIRECTORY, "curriculum_v1.json")
    cases = {row["case_id"]: row for row in catalog["cases"]}
    evidence = {row["evidence_id"]: row for row in catalog["evidence"]}
    assert len(cases) == len(catalog["cases"])
    assert len(evidence) == len(catalog["evidence"])
    lessons = {
        row["order"]: read_relative(DIRECTORY, row["path"])
        for row in catalog["lessons"]
    }
    assert set(lessons) == set(range(1, 21))
    return {
        "lessons": lessons,
        "evidence": evidence,
        "charts": {
            name: read_relative(ROOT, case["chart_path"])
            for name, case in cases.items()
        },
    }


def citations(text: str) -> set[str]:
    names = CITATION.findall(text)
    assert all(ALIAS.fullmatch(name) for name in names)
    return set(names)


def actual_alias(chart: dict, name: str) -> tuple[dict, object]:
    group = "c" if name.startswith("c") else "r"
    rows = [row for row in chart["aliases"][group] if row["alias"] == name]
    assert len(rows) == 1
    alias = rows[0]
    assert alias["scope"] == chart["scope"]
    documents = [
        row
        for row in chart["documents"]
        if row["document_id"] == alias["ref"]["document_id"]
    ]
    assert len(documents) == 1
    payload, path = documents[0]["payload"], alias["ref"]["path"]
    value = payload if path == "" else pointer(payload, path)
    if group == "r":
        assert value["met"] is True and value["rule_id"] == alias["rule_id"]
    return alias, value


def allowed_citations(study: dict, case_id: str, evidence_ids: list[str]) -> set[str]:
    assert evidence_ids
    chart = study["charts"][case_id]
    allowed = set()
    for identity in evidence_ids:
        evidence = study["evidence"][identity]
        assert evidence["case_id"] == case_id
        chart_alias, observed = actual_alias(chart, evidence["c_alias"])
        relative = evidence["relative_path"]
        observed = observed if relative == "" else pointer(observed, relative)
        assert json.dumps(observed, sort_keys=True, ensure_ascii=False) == json.dumps(
            evidence["expected"], sort_keys=True, ensure_ascii=False
        )
        allowed.add(chart_alias["alias"])
        for name in evidence["r_aliases"]:
            rule_alias, _hit = actual_alias(chart, name)
            assert chart_alias["alias"] in rule_alias["evidence_aliases"]
            allowed.add(name)
    return allowed


def assert_displayed_citations(
    study: dict, text: str, case_id: str, evidence_ids: list[str]
) -> None:
    displayed = citations(text)
    allowed = allowed_citations(study, case_id, evidence_ids)
    assert displayed <= allowed
    assert any(name.startswith("c") for name in displayed)
    for name in displayed:
        actual_alias(study["charts"][case_id], name)


@pytest.mark.parametrize("order", range(1, 21))
def test_worked_example_citations_match_the_exact_case_and_evidence(
    study, order
) -> None:
    examples = study["lessons"][order]["worked_examples"]
    assert examples
    for example in examples:
        assert_displayed_citations(
            study, example["text"], example["case_id"], example["evidence_ids"]
        )


@pytest.mark.parametrize("order,number", [(a, b) for a in range(1, 21) for b in (1, 2)])
def test_quiz_citations_are_evidence_scoped_or_absent_for_concepts(
    study, order: int, number: int
) -> None:
    quizzes = study["lessons"][order]["quiz"]
    assert len(quizzes) == 2
    quiz = quizzes[number - 1]
    visible = "\n".join(
        [
            quiz["question"],
            *(row["text"] for row in quiz["options"]),
            quiz["explanation"],
        ]
    )
    basis = quiz["basis"]
    if basis["kind"] == "concept":
        assert citations(visible) == set()
        return
    assert basis["kind"] in ("chart_observation", "matched_rule")
    identity = basis["evidence_id"]
    evidence = study["evidence"][identity]
    allowed = allowed_citations(study, evidence["case_id"], [identity])
    assert citations(visible) <= allowed
    # A distractor option cannot supply the answer explanation's required c.
    assert_displayed_citations(
        study, quiz["explanation"], evidence["case_id"], [identity]
    )

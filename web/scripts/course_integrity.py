"""Bind teaching text and answers to independently checked case-local evidence."""

from __future__ import annotations

import re

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from course_bundle import ERROR, PREFIX, need
from learning_samples.chart_integrity import resolve_ref, verify_chart
from learning_samples.common import pointer, same
from learning_samples.projection import project_learning

SAMPLES = "docs/v4/contracts/samples/"
TERMS = "mingjing_core/knowledge/p8_glossary/terms_v1.json"
SOURCES = "mingjing_core/knowledge/p8_glossary/sources_v1.json"


def local_refs(value: object) -> None:
    if type(value) is dict:
        if "$ref" in value:
            need(type(value["$ref"]) is str and value["$ref"].startswith("#/$defs/"))
        for child in value.values():
            local_refs(child)
    elif type(value) is list:
        for child in value:
            local_refs(child)


def schema_check(value: dict, schema: dict) -> None:
    local_refs(schema)
    Draft202012Validator.check_schema(schema)
    need(not next(Draft202012Validator(schema).iter_errors(value), None))


def citations(text: str, allowed: set[str]) -> None:
    need(type(text) is str)
    names = re.findall(r"〔([^〕]*)〕", text)
    need(
        all(
            re.fullmatch(r"[cr][1-9][0-9]*", name) and name in allowed for name in names
        )
    )


def cases_checked(curriculum: dict, values: dict, hashes: dict) -> dict:
    cases = {}
    for case in curriculum["cases"]:
        name, system = case["case_id"], case["system"]
        need(name == f"ayuan-{system}" and name not in cases)
        chart_path, learning_path = case["chart_path"], case["learning_path"]
        need(chart_path == f"{SAMPLES}ayuan_{system}.json")
        need(learning_path == f"{SAMPLES}learning-ayuan-{system}.json")
        need(
            hashes[chart_path] == case["chart_sha256"]
            and hashes[learning_path] == case["learning_sha256"]
        )
        chart, learning = values[chart_path], values[learning_path]
        need(same(case["scope"], chart["scope"]))
        documents, aliases = verify_chart(chart, system)
        projected = project_learning(learning, chart, system)
        points = {point["point_id"] for point in learning["points"]}
        need(len(set(case["learning_point_ids"])) == len(case["learning_point_ids"]))
        need(set(case["learning_point_ids"]) <= points)
        cases[name] = {
            "chart": chart,
            "documents": documents,
            "aliases": aliases,
            "points": points,
            "projection": projected,
            "operation": chart["scope"]["operation_id"],
        }
    need(set(cases) == {"ayuan-bazi", "ayuan-ziwei", "ayuan-astro"})
    return cases


def evidence_checked(curriculum: dict, cases: dict) -> dict:
    evidence = {}
    for item in curriculum["evidence"]:
        need(item["evidence_id"] not in evidence)
        case = cases[item["case_id"]]
        row = case["aliases"][item["c_alias"]]
        need(row["alias"].startswith("c"))
        actual = pointer(
            resolve_ref(case["documents"], row["ref"]), item["relative_path"]
        )
        need(same(actual, item["expected"]))
        if item["role"] == "primary":
            need(row["ref"] in case["chart"]["view"]["primary"])
        elif item["role"] == "basis":
            need(row["ref"]["path"].startswith("/time_basis/"))
        elif item["role"] == "rule_input":
            need(bool(item["r_aliases"]))
        else:
            need(False)
        for name in item["r_aliases"]:
            rule = case["aliases"][name]
            need(name.startswith("r") and item["c_alias"] in rule["evidence_aliases"])
            need(resolve_ref(case["documents"], rule["ref"])["met"] is True)
        evidence[item["evidence_id"]] = item
    need(len(evidence) == 20)
    return evidence


def quiz_checked(
    quiz: dict, evidence: dict, sources: set[str], worked: set[str]
) -> set[str]:
    options = quiz["options"]
    need(len({option["option_id"] for option in options}) == len(options))
    correct = [
        option for option in options if option["option_id"] == quiz["correct_option_id"]
    ]
    need(len(correct) == 1)
    basis = quiz["basis"]
    need(same(correct[0]["value"], basis["expected"]))
    need(
        all(
            not same(option["value"], basis["expected"])
            for option in options
            if option is not correct[0]
        )
    )
    if basis["kind"] == "concept":
        need(set(basis["source_ids"]) <= sources)
        return set()
    item = evidence[basis["evidence_id"]]
    need(item["case_id"] in worked and same(item["expected"], basis["expected"]))
    if basis["kind"] == "matched_rule":
        need(item["role"] == "rule_input" and bool(item["r_aliases"]))
    else:
        need(basis["kind"] == "chart_observation")
    return {item["c_alias"], *item["r_aliases"]}


def lesson_checked(
    lesson: dict, earlier: set[str], cases: dict, evidence: dict, sources: set[str]
) -> None:
    need(set(lesson["prerequisite_ids"]) <= earlier)
    need(len(set(lesson["prerequisite_ids"])) == len(lesson["prerequisite_ids"]))
    declared = set(lesson["source_ids"])
    need(declared <= sources)
    for difference in lesson["school_differences"]:
        need(set(difference["source_ids"]) <= declared)
    allowed, worked = set(), set()
    for example in lesson["worked_examples"]:
        case_id = example["case_id"]
        worked.add(case_id)
        need(set(example["learning_point_ids"]) <= cases[case_id]["points"])
        names = set()
        for name in example["evidence_ids"]:
            item = evidence[name]
            need(item["case_id"] == case_id)
            names.update({item["c_alias"], *item["r_aliases"]})
        citations(example["text"], names)
        allowed.update(names)
    need(len({quiz["quiz_id"] for quiz in lesson["quiz"]}) == len(lesson["quiz"]))
    need(
        {quiz["quiz_id"] for quiz in lesson["quiz"]}
        == {lesson["lesson_id"] + "-q1", lesson["lesson_id"] + "-q2"}
    )
    for quiz in lesson["quiz"]:
        names = quiz_checked(quiz, evidence, declared, worked)
        for text in [
            quiz["question"],
            quiz["explanation"],
            *(option["text"] for option in quiz["options"]),
        ]:
            citations(text, names)
        allowed.update(names)
    for text in [lesson["title"], *lesson["paragraphs"], *lesson["objectives"]]:
        citations(text, allowed)


def verify_bundle(values: dict, hashes: dict) -> dict:
    try:
        curriculum = values[PREFIX + "curriculum_v1.json"]
        lesson_schema = values["docs/v4/contracts/learning_lessons.schema.json"]
        schema_check(curriculum, lesson_schema)
        schema_check(values[TERMS], values["docs/v4/contracts/glossary.schema.json"])
        schema_check(
            values[SOURCES], values["docs/v4/contracts/glossary_sources.schema.json"]
        )
        registry = curriculum["source_registry"]
        need(registry["path"] == SOURCES and registry["sha256"] == hashes[SOURCES])
        need(registry["version"] == values[SOURCES]["version"])
        sources = {row["source_id"] for row in values[SOURCES]["sources"]}
        need(len(sources) == 39 and len(values[TERMS]["entries"]) == 212)
        cases = cases_checked(curriculum, values, hashes)
        evidence = evidence_checked(curriculum, cases)
        earlier, lessons = set(), []
        for entry in curriculum["lessons"]:
            need(entry["path"] == f"lessons/{entry['lesson_id']}.json")
            lesson = values[PREFIX + entry["path"]]
            schema_check(lesson, lesson_schema)
            need(
                all(
                    same(lesson[key], entry[key])
                    for key in ("lesson_id", "order", "title", "level", "status")
                )
            )
            need(
                entry["lesson_id"] not in earlier and entry["order"] == len(lessons) + 1
            )
            lesson_checked(lesson, earlier, cases, evidence, sources)
            earlier.add(entry["lesson_id"])
            lessons.append(lesson)
        need(len(lessons) == curriculum["lesson_count"] == 20)
        need(
            sum(len(lesson["quiz"]) for lesson in lessons)
            == curriculum["quiz_count"]
            == 40
        )
        return {
            "cases": cases,
            "evidence": evidence,
            "lessons": lessons,
            "source_ids": sources,
        }
    except (
        KeyError,
        TypeError,
        ValueError,
        IndexError,
        RecursionError,
        SchemaError,
        OverflowError,
    ):
        raise ValueError(ERROR) from None

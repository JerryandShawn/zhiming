"""Explicit browser-only course fields; raw chart and answer values stay offline."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from course_bundle import COMMIT, MANIFEST_SHA, PREFIX, ROOT, need
from course_integrity import SOURCES, verify_bundle
from study_glossary import plain

WEB = ROOT / "web"
SUMMARIES = {
    "primary": "已在该合成样例主盘核对；不细分或新造计算别名。",
    "basis": "已核对时间口径；本页不下发原始时刻与完整候选盘。",
    "rule_input": "仅核对原生候选条件，不代表格局成立或现实结果。",
}


def selected(value: dict, keys: tuple[str, ...]) -> dict:
    return {key: copy.deepcopy(value[key]) for key in keys}


def text_only(value: object) -> None:
    if type(value) is str:
        plain(value)
    elif type(value) is dict:
        for child in value.values():
            text_only(child)
    elif type(value) is list:
        for child in value:
            text_only(child)


def public_quiz(quiz: dict) -> dict:
    return {
        **selected(quiz, ("quiz_id", "question", "correct_option_id", "explanation")),
        "options": [
            selected(option, ("option_id", "text")) for option in quiz["options"]
        ],
        "basis": selected(quiz["basis"], ("kind",)),
        "evidence_ids": [quiz["basis"]["evidence_id"]]
        if "evidence_id" in quiz["basis"]
        else [],
        "source_ids": list(quiz["basis"].get("source_ids", [])),
    }


def public_lesson(lesson: dict) -> dict:
    return {
        **selected(
            lesson,
            (
                "lesson_id",
                "order",
                "title",
                "level",
                "status",
                "prerequisite_ids",
                "objectives",
                "paragraphs",
                "source_ids",
                "pending_review",
            ),
        ),
        "worked_examples": [
            selected(example, ("case_id", "text", "evidence_ids", "learning_point_ids"))
            for example in lesson["worked_examples"]
        ],
        "quiz": [public_quiz(quiz) for quiz in lesson["quiz"]],
        "school_differences": [
            selected(row, ("school", "note", "source_ids"))
            for row in lesson["school_differences"]
        ],
    }


def project_course(values: dict, hashes: dict) -> dict:
    verified = verify_bundle(values, hashes)
    curriculum = values[PREFIX + "curriculum_v1.json"]
    contexts = {
        name: hashlib.sha256(case["operation"].encode("utf8")).hexdigest()
        for name, case in verified["cases"].items()
    }
    result = {
        "format": "frontend-course-v1",
        "title": curriculum["title"],
        "status": curriculum["status"],
        "synthetic_only": True,
        "lessons": [public_lesson(lesson) for lesson in verified["lessons"]],
        "cases": [
            {
                "case_id": name,
                "context_sha256": contexts[name],
                "learning": copy.deepcopy(case["projection"]),
            }
            for name, case in verified["cases"].items()
        ],
        "evidence": [
            {
                **selected(
                    item, ("evidence_id", "case_id", "c_alias", "r_aliases", "role")
                ),
                "context_sha256": contexts[item["case_id"]],
                "summary": SUMMARIES[item["role"]],
            }
            for item in verified["evidence"].values()
        ],
        "sources": [
            selected(
                row,
                (
                    "source_id",
                    "title",
                    "kind",
                    "verification_status",
                    "edition_page_status",
                ),
            )
            for row in values[SOURCES]["sources"]
        ],
        "provenance": {
            "source_commit": COMMIT,
            "manifest_sha256_lf_utf8": MANIFEST_SHA,
            "input_sha256_lf_utf8": dict(sorted(hashes.items())),
        },
        "effects": {"model_calls": 0, "user_writes": 0, "network_calls": 0},
        "limits": [
            "仅供合成样例学习，课程仍待专业复核。",
            "测验答案按本次固定样例离线核对，不构成现实预测或专业认证。",
            "别名只在所属样例与上下文有效；不连接真实资料或保存学习进度。",
        ],
    }
    text_only(result)
    return result


def export_course(output: Path, values: dict, hashes: dict) -> dict:
    output = output.resolve()
    need(WEB in output.parents and not output.exists())
    projected = project_course(values, hashes)
    body = (
        json.dumps(projected, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf8")
    manifest = {
        "format": "frontend-course-export-v1",
        "source_commit": COMMIT,
        "synthetic_only": True,
        "lessons": 20,
        "quizzes": 40,
        "file": "course.json",
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    # Validation and encoding finish before creating any output, as in the older exporter.
    output.mkdir(parents=True, exist_ok=False)
    (output / "course.json").write_bytes(body)
    with (output / "manifest.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest

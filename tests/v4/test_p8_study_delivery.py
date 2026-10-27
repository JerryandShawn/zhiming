"""Frontend handoff pins real assets and visible lesson citations, offline."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COURSE = ROOT / "mingjing_core/knowledge/p8_learning_lessons"


def read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def citations(text: str) -> set[str]:
    return set(re.findall(r"〔([cr][1-9][0-9]*)〕", text))


def test_delivery_manifest_pins_all_assets_using_lf_utf8() -> None:
    manifest = read(ROOT / "docs/v4/contracts/study_delivery_manifest.json")
    assert manifest["counts"] == {"terms": 212, "lessons": 20, "quizzes": 40}
    paths = [row["path"] for row in manifest["assets"]]
    assert len(paths) == len(set(paths))
    for row in manifest["assets"]:
        path = (ROOT / row["path"]).resolve()
        assert path.is_relative_to(ROOT) and path.is_file()
        normalized = path.read_text(encoding="utf8").replace("\r\n", "\n").encode()
        assert hashlib.sha256(normalized).hexdigest() == row["sha256_lf_utf8"]
    course = read(COURSE / "curriculum_v1.json")
    assert {
        "mingjing_core/knowledge/p8_learning_lessons/" + row["path"]
        for row in course["lessons"]
    } <= set(paths)


@pytest.mark.parametrize("number", range(1, 21))
def test_visible_lesson_aliases_belong_to_declared_case_evidence(number: int) -> None:
    course = read(COURSE / "curriculum_v1.json")
    evidence = {row["evidence_id"]: row for row in course["evidence"]}
    lesson = read(COURSE / f"lessons/lesson-{number:02}.json")
    for example in lesson["worked_examples"]:
        allowed = set()
        for identity in example["evidence_ids"]:
            row = evidence[identity]
            assert row["case_id"] == example["case_id"]
            allowed.update([row["c_alias"], *row["r_aliases"]])
        assert citations(example["text"]) <= allowed
    for quiz in lesson["quiz"]:
        basis = quiz["basis"]
        if basis["kind"] == "concept":
            assert not citations(quiz["explanation"])
        else:
            row = evidence[basis["evidence_id"]]
            assert citations(quiz["explanation"]) <= {row["c_alias"], *row["r_aliases"]}

"""QA remains honest about the known boundary-text erratum and source limits."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from mingjing_core.adapters.charts.benchmarks.final_prep_v7 import DIRECTORY
from mingjing_core.adapters.charts.benchmarks.skill_qa_v7 import (
    audit_library,
    inspect_chapter,
)
from mingjing_core.skills.loader import SkillLibrary

LIBRARY = SkillLibrary()
PAIRS = [
    (system, row["topic"])
    for system in LIBRARY.catalog["systems"]
    for row in LIBRARY.chapters(system)
]


@pytest.mark.parametrize(("system", "topic"), PAIRS)
def test_every_chapter_inventory_preserves_actual_applicability_and_references(
    system: str, topic: str
) -> None:
    report = json.loads((DIRECTORY / "skill_inventory.json").read_bytes())
    saved = next(
        row
        for row in report["chapters"]
        if (row["system"], row["topic"]) == (system, topic)
    )
    assert saved == inspect_chapter(LIBRARY.load(system, topic))
    assert saved["context_utf8_bytes"] <= 5500
    assert saved["required_fields"] and saved["sources"]


def test_known_erratum_is_disclosed_not_silently_marked_green() -> None:
    report = audit_library()
    assert report["chapter_count"] == 32
    assert len(report["systems"]) == 5
    assert report["issues"] == [
        {
            "system": "bazi",
            "topic": "basics",
            "code": "erratum_jie_boundary_2_minutes_vs_7200_seconds",
        }
    ]
    notes = (DIRECTORY / "skill_errata.md").read_text(encoding="utf-8")
    assert "未修改原章节" in notes and "7200" in notes and "±2小时" in notes
    assert "未重开PDF" in notes


@pytest.mark.parametrize(
    "mutation", ["heading", "locator", "applicability", "required"]
)
def test_missing_review_evidence_is_detected(mutation: str) -> None:
    loaded = deepcopy(LIBRARY.load("astro", "aspects"))
    if mutation == "heading":
        loaded["text"] = loaded["text"].replace("## 适用前提", "## 范围")
        expected = "missing_heading:适用前提"
    elif mutation == "locator":
        loaded["metadata"]["sources"][0].pop("locator")
        expected = "source_locator_missing:0"
    elif mutation == "applicability":
        loaded["metadata"]["wiring_applicability"]["enforcement_owner"] = "unknown"
        expected = "applicability_owner_missing"
    else:
        loaded["metadata"]["required_fields"] = []
        expected = "missing_metadata:required_fields"
    assert expected in inspect_chapter(loaded)["issues"]

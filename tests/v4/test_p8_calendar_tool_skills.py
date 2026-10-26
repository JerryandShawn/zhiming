"""New tool chapters retain real-field roots, provenance and honest examples."""

from __future__ import annotations

import json
import re
from pathlib import Path

from mingjing_core.adapters.charts.tool_evidence import pointer
from mingjing_core.skills import SkillLibrary

ROOT = Path(__file__).resolve().parents[2]


def test_calendar_tool_topics_do_not_replace_any_original_skill_system() -> None:
    library = SkillLibrary()
    expected = {"bazi": 10, "ziwei": 6, "astro": 5, "tarot": 7}
    assert {key: len(library.chapters(key)) for key in expected} == expected
    assert [row["topic"] for row in library.chapters("calendar-tools")] == [
        "daily-transit",
        "window-search",
        "almanac",
        "synastry",
    ]
    assert len(library.catalog["systems"]) == 5


def test_almanac_field_requirements_resolve_against_the_real_calculated_sample() -> (
    None
):
    sample = json.loads(
        (ROOT / "docs/v4/contracts/samples/almanac-20261021.json").read_text(
            encoding="utf8"
        )
    )
    chapter = SkillLibrary().load("calendar-tools", "almanac")
    assert chapter["metadata"]["artifact_root"] == "P8ToolEvidenceResult"
    for path in chapter["metadata"]["required_fields"]:
        assert pointer(sample, path) is not None
    assert set(chapter["metadata"]["rule_ids"]) == {
        row["rule_id"] for row in sample["rule_hits"]
    }


def test_tool_chapters_use_explicit_alias_formats_instead_of_fake_live_aliases() -> (
    None
):
    library = SkillLibrary()
    for chapter in library.chapters("calendar-tools"):
        result = library.load("calendar-tools", chapter["topic"])
        text = result["text"]
        assert "〔c#〕〔r#〕" in text
        assert not re.search(r"〔[cr][1-9][0-9]*〕", text)
        assert "aliases.r" in text and "真实" in text
        assert "存疑/待核" in text
        assert result["metadata"]["artifact_root"] == "P8ToolEvidenceResult"


def test_synastry_keeps_consent_before_data_and_separates_the_explicit_date() -> None:
    text = SkillLibrary().load("calendar-tools", "synastry")["text"]
    assert text.index("consent必须精确为user_confirmed") < text.index("读取实际两盘")
    for phrase in (
        "不先算后问",
        "不在拒绝里泄露",
        "不自动授权保存",
        "as_of_date由主线Clock明确注入",
        "不读本机",
        "双方意愿",
        "倒推仍冻结",
    ):
        assert phrase in text

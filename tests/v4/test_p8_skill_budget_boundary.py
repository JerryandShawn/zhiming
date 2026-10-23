"""Exact complete-context byte budgets; they are not model-token measurements."""

from __future__ import annotations

import hashlib
import json

import pytest

from mingjing_core.skills.loader import MAX_CONTEXT_UTF8_BYTES, SkillLibrary


def _library(tmp_path, target: int, unit: str) -> tuple[SkillLibrary, str]:
    root = tmp_path / "skills"
    (root / "bazi").mkdir(parents=True)
    version = "synthetic-budget-v1"
    tail = "\n## 参考来源\n合成来源保留，不作盘面依据。"
    wrapper = f'<技能 system="bazi" topic="budget" version="{version}">\n\n</技能>'
    remaining = target - len((wrapper + tail).encode("utf8"))
    size = len(unit.encode("utf8"))
    text = unit * (remaining // size) + "x" * (remaining % size) + tail
    (root / "bazi/chapter.md").write_text(text, encoding="utf8", newline="\n")
    catalog = {
        "version": version,
        "systems": {"bazi": {"chapters": [{"topic": "budget", "file": "chapter.md"}]}},
    }
    (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf8")
    return SkillLibrary(root), text


@pytest.mark.parametrize("unit", ["x", "中", "🧭", "e\u0301"])
def test_exact_limit_preserves_complete_text_source_tail_and_hash(
    tmp_path, unit: str
) -> None:
    library, text = _library(tmp_path, MAX_CONTEXT_UTF8_BYTES, unit)
    result = library.load("bazi", "budget")
    assert result["context_utf8_bytes"] == 5500
    assert result["text"] == text and "合成来源保留" in result["context"]
    assert result["sha256"] == hashlib.sha256(text.encode("utf8")).hexdigest()
    assert result["token_budget"]["accounted_units"] == 5500
    assert "not a measured model-token count" in result["token_budget"]["accounting"]


@pytest.mark.parametrize("unit", ["x", "中", "🧭", "e\u0301"])
def test_one_byte_over_limit_is_rejected_without_truncating_the_asset(
    tmp_path, unit: str
) -> None:
    library, text = _library(tmp_path, MAX_CONTEXT_UTF8_BYTES + 1, unit)
    before = (library.root / "bazi/chapter.md").read_bytes()
    with pytest.raises(ValueError, match="章节超出保守上下文预算"):
        library.load("bazi", "budget")
    assert (library.root / "bazi/chapter.md").read_bytes() == before
    assert before.decode("utf8") == text

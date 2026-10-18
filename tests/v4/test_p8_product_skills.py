"""Product skill assets are bounded, read-only, sourced and progressively loaded."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from mingjing_core.adapters.charts.rules import load_registry
from mingjing_core.skills import SkillLibrary, chart_skill
from mingjing_core.skills.loader import MAX_CONTEXT_UTF8_BYTES, ROOT


def test_all_systems_have_requested_chapter_coverage_and_open_frontmatter() -> None:
    library = SkillLibrary()
    assert {key: len(library.chapters(key)) for key in library.catalog["systems"]} == {
        "bazi": 10,
        "ziwei": 6,
        "astro": 5,
        "tarot": 7,
    }
    for system in library.catalog["systems"]:
        manifest = (ROOT / system / "SKILL.md").read_text(encoding="utf-8")
        assert manifest.startswith(f"---\nname: {system}\ndescription: ")
        assert manifest.split("---", 2)[2].strip()
        for chapter in library.chapters(system):
            assert f"({chapter['file']})" in manifest


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro", "tarot"])
def test_every_chapter_has_substantive_structure_sources_and_bounded_context(
    system: str,
) -> None:
    library = SkillLibrary()
    for chapter in library.chapters(system):
        result = library.load(system, chapter["topic"])
        text = result["text"]
        for heading in (
            "方法步骤",
            "需要的盘面字段",
            "各流派观点与分歧",
            "适用前提",
            "反例与常见误读",
            "表达示例",
            "参考来源",
            "对应的规则命中 rule_id 列表",
        ):
            assert f"## {heading}" in text
        assert len(text) >= 500
        assert chapter["required_fields"]
        assert all(field.startswith("/") for field in chapter["required_fields"])
        assert all(
            source["locator"] and source["url"].startswith("https://")
            for source in chapter["sources"]
        )
        assert all(source["url"] in text for source in chapter["sources"])
        assert all(field in text for field in chapter["required_fields"])
        for group in ("conditional_fields", "additional_interfaces"):
            for interface in chapter.get(group, []):
                assert all(
                    path.startswith("/") and path in text for path in interface["paths"]
                )
        assert result["context_utf8_bytes"] == len(result["context"].encode("utf-8"))
        assert result["context_utf8_bytes"] <= MAX_CONTEXT_UTF8_BYTES < 6000
        assert (
            "not a measured model-token count" in result["token_budget"]["accounting"]
        )
        assert result["context"].startswith(
            f'<技能 system="{system}" topic="{chapter["topic"]}"'
        )
        assert result["context"].endswith("</技能>")
        assert result["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_every_registered_bazi_rule_is_mapped_to_a_skill_chapter() -> None:
    library = SkillLibrary()
    expected = {row["rule_id"] for row in load_registry()["rules"]}
    documented = {
        ident for row in library.chapters("bazi") for ident in row["rule_ids"]
    }
    assert documented == expected
    for row in library.chapters("bazi"):
        content = library.load("bazi", row["topic"])["text"]
        assert all(ident in content for ident in row["rule_ids"])


@pytest.mark.parametrize(
    "system,topic",
    [("../bazi", "basics"), ("bazi", "../loader"), ("bazi", ""), ("other", "x")],
)
def test_unregistered_or_path_shaped_input_is_rejected(system: str, topic: str) -> None:
    with pytest.raises(ValueError):
        chart_skill(system, topic)


def test_metadata_cannot_mutate_library_and_loading_does_not_rewrite_assets() -> None:
    before = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in ROOT.rglob("*.md")
    }
    library = SkillLibrary()
    chapters = library.chapters("bazi")
    chapters[0]["required_fields"].clear()
    loaded = library.load("bazi", "basics")
    loaded["metadata"]["sources"].clear()
    assert library.load("bazi", "basics")["metadata"]["required_fields"]
    assert library.load("bazi", "basics")["metadata"]["sources"]
    after = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in ROOT.rglob("*.md")
    }
    assert before == after


def test_context_over_budget_is_rejected_without_truncating_sources() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "bazi").mkdir()
        (root / "bazi" / "chapter.md").write_text("中" * 2000, encoding="utf-8")
        catalog = {
            "version": "test-v1",
            "systems": {
                "bazi": {"chapters": [{"topic": "basics", "file": "chapter.md"}]}
            },
        }
        (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        with pytest.raises(ValueError, match="预算"):
            SkillLibrary(root).load("bazi", "basics")


def test_catalog_cannot_load_a_parent_file_even_if_name_was_registered() -> None:
    library = SkillLibrary()
    library.catalog["systems"]["bazi"]["chapters"][0]["file"] = "../README.md"
    with pytest.raises(ValueError, match="路径"):
        library.load("bazi", "basics")


def test_future_fields_are_explicit_and_rectification_never_grants_write_authority() -> (
    None
):
    library = SkillLibrary()
    for system, topic in (
        ("bazi", "rectification"),
        ("ziwei", "mutagens"),
        ("astro", "returns"),
    ):
        loaded = library.load(system, topic)
        assert loaded["metadata"]["pending_fields"]
        assert any(
            label in loaded["text"] for label in ("待接入", "待核验", "待主线接入")
        )
    rectification = library.load("bazi", "rectification")
    assert "/profile_update_allowed" in rectification["text"]
    assert "以记录为准" in rectification["text"]
    assert "原“评分→前三候选→合成前三命中率”的方法已被撤回" in rectification["text"]
    workbench = library.load("bazi", "rectification-rules")["text"]
    assert all(
        word in workbench for word in ("冻结", "留出", "1000次", "分不出来", "低优先")
    )


def test_tarot_skill_uses_fixed_public_draw_and_protects_near_repeat_question() -> None:
    loaded = chart_skill("tarot", "spread")
    assert (
        loaded["metadata"]["artifact_root"]
        == "TarotService.get_for_reading public draw"
    )
    for contract in ("24小时", "固定", "未翻开", "原话溯源", "owner"):
        assert contract in loaded["text"]

"""Local asset profile, provenance shape and manifest/catalog consistency."""

from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlsplit

import pytest
from jsonschema import Draft202012Validator, ValidationError

from mingjing_core.skills import SkillLibrary
from tests.v4.p8_skill_asset_context import ASSETS, CONTRACTS, json_asset, manifest

SCHEMA = json_asset(CONTRACTS / "skill_assets.schema.json")
CATALOG = json_asset(ASSETS / "catalog.json")
SYSTEMS = list(CATALOG["systems"])


def test_catalog_has_a_valid_complete_local_profile() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    Draft202012Validator(SCHEMA).validate(CATALOG)
    assert len(SYSTEMS) == 5
    assert sum(len(row["chapters"]) for row in CATALOG["systems"].values()) == 32


@pytest.mark.parametrize("system", SYSTEMS)
def test_manifests_and_real_chapter_inventory_match_catalog(system: str) -> None:
    package = CATALOG["systems"][system]
    path = ASSETS / system / "SKILL.md"
    text = path.read_text(encoding="utf8")
    metadata = manifest(text)
    assert metadata == {"name": package["name"], "description": package["description"]}
    assert metadata["name"] == system
    assert "版本：" + CATALOG["version"] in text
    topics = [row["topic"] for row in package["chapters"]]
    filenames = [row["file"] for row in package["chapters"]]
    assert len(set(topics)) == len(topics) and len(set(filenames)) == len(filenames)
    assert {row.name for row in path.parent.glob("*.md")} == set(filenames) | {
        "SKILL.md"
    }
    for chapter in package["chapters"]:
        assert text.count("(" + chapter["file"] + ")") == 1
        assert chapter["topic"] in text and chapter["question_types"]


@pytest.mark.parametrize("system", SYSTEMS)
def test_source_records_remain_local_metadata_not_an_original_edition_claim(
    system: str,
) -> None:
    library = SkillLibrary()
    for chapter in library.chapters(system):
        loaded = library.load(system, chapter["topic"])
        assert "存疑/待核" in loaded["text"]
        for source in chapter["sources"]:
            assert source["title"].strip() and source["locator"].strip()
            assert urlsplit(source["url"]).scheme == "https"
            assert urlsplit(source["url"]).netloc
            assert source["url"] in loaded["text"]
        assert loaded["metadata"]["status"] == "draft_requires_owner_review"


@pytest.mark.parametrize(
    "mutation",
    ["empty_locator", "empty_sources", "http", "bad_escape", "path", "bool_visible"],
)
def test_local_profile_rejects_invalid_source_pointer_or_metadata_shape(
    mutation: str,
) -> None:
    catalog = deepcopy(CATALOG)
    chapter = catalog["systems"]["bazi"]["chapters"][0]
    if mutation == "empty_locator":
        chapter["sources"][0]["locator"] = " "
    elif mutation == "empty_sources":
        chapter["sources"] = []
    elif mutation == "http":
        chapter["sources"][0]["url"] = "http://synthetic.invalid/source"
    elif mutation == "bad_escape":
        chapter["required_fields"] = ["/data/~2"]
    elif mutation == "path":
        chapter["file"] = "../outside.md"
    else:
        chapter["visible_by_default"] = 1
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(catalog)


@pytest.mark.parametrize(
    "text",
    [
        "name: bazi\ndescription: missing delimiters",
        "---\nname: bazi\ndescription: \n---\nbody",
        "---\nname: bazi\nname: astro\ndescription: duplicated\n---\nbody",
        "---\nname: bazi\ndescription: ok\nexecute: true\n---\nbody",
    ],
)
def test_project_manifest_subset_rejects_ambiguous_or_empty_metadata(text: str) -> None:
    with pytest.raises(ValueError, match="^local_manifest_"):
        manifest(text)


def test_duplicate_json_keys_cannot_hide_a_catalog_change(tmp_path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text('{"version":"first","version":"second"}', encoding="utf8")
    with pytest.raises(ValueError, match="^duplicate_asset_key$"):
        json_asset(path)


def test_reference_policy_keeps_u12_boundary_tools_and_tarot_types_distinct() -> None:
    for system in ("bazi", "ziwei", "astro", "calendar-tools"):
        text = (ASSETS / system / "SKILL.md").read_text(encoding="utf8")
        assert (
            "U12" in text and "边界" in text and "工具" in text and "met=true" in text
        )
        assert "非八字rule_hits不制造" not in text
    tarot = (ASSETS / "tarot/SKILL.md").read_text(encoding="utf8")
    assert "真实〔t#〕" in tarot and "不能把它说成牌义或新抽牌依据" in tarot
    assert "塔罗技能不生成八字U12结构r" in tarot
    assert CATALOG["version"] == "p8-skills-draft-2026-10-21-v2.4"

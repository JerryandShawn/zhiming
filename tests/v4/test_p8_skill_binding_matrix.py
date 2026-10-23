"""Resolve registered pointers only in their declared, actually available roots."""

from __future__ import annotations

import hashlib

import pytest

from mingjing_core.domain.calculation import CalculationArtifact, CalculationProfile
from mingjing_core.skills import SkillLibrary
from tests.v4.p8_skill_asset_context import (
    ASSETS,
    CONTRACTS,
    bindings,
    groups,
    json_asset,
    resolved_values,
    source_root,
)

CATALOG = json_asset(ASSETS / "catalog.json")
MATRIX = json_asset(CONTRACTS / "skill_bindings.json")
GROUPS = groups(CATALOG)
BINDINGS = bindings(MATRIX)
AVAILABLE = [
    key
    for key, ident in BINDINGS.items()
    if MATRIX["sources"][ident]["status"] == "available"
]
UNAVAILABLE = [key for key in BINDINGS if key not in AVAILABLE]


def _id(key: tuple) -> str:
    return "/".join(item for item in key if item)


def test_matrix_covers_exactly_every_registered_chapter_and_capability() -> None:
    assert MATRIX["catalog_version"] == CATALOG["version"]
    assert len(MATRIX["chapters"]) == 32
    assert set(BINDINGS) == set(GROUPS)
    assert len(BINDINGS) == 37
    assert len(AVAILABLE) == 37 and not UNAVAILABLE
    assert len({(row["system"], row["topic"]) for row in MATRIX["chapters"]}) == 32


@pytest.mark.parametrize("key", AVAILABLE, ids=_id)
def test_available_bindings_resolve_all_paths_in_the_exact_real_root(
    key: tuple,
) -> None:
    source = MATRIX["sources"][BINDINGS[key]]
    expected_root, paths = GROUPS[key]
    assert source["artifact_root"] == expected_root
    root = source_root(source)
    assert len(resolved_values(root, paths)) == len(paths)
    if source.get("tool_version"):
        assert root["version"] == source["tool_version"]
    if source.get("technique"):
        assert root["technique"] == source["technique"]


def test_explicitly_unavailable_roots_cannot_be_silently_substituted() -> None:
    with pytest.raises(ValueError, match="^skill_root_unavailable$"):
        source_root({"status": "unavailable", "sample": "samples/ayuan_bazi.json"})


def test_native_saved_artifacts_are_original_roots_with_actual_method_profiles() -> (
    None
):
    directory = CONTRACTS / "samples/skill-bindings"
    manifest = json_asset(directory / "manifest.json")
    bundle = json_asset(directory / "calculation-bundle.json")
    assert (
        manifest["method_policy"]
        == "legacy_explicit_entry_not_default_true_solar_reading"
    )
    assert manifest["synthetic"] is True and not bundle["errors"]
    for row in manifest["files"]:
        assert (
            hashlib.sha256((directory / row["file"]).read_bytes()).hexdigest()
            == row["sha256"]
        )
    assert manifest["actual_profiles"] == bundle["profiles"]
    for system in ("bazi", "ziwei"):
        artifact = source_root(MATRIX["sources"][system + "_artifact"])
        assert CalculationArtifact.model_validate(artifact).model_dump() == artifact
        assert artifact == bundle["artifacts"][artifact["id"]]
        profile = bundle["profiles"][artifact["profile_id"]]
        assert CalculationProfile.model_validate(profile).model_dump() == profile
        assert "legacy_explicit" in MATRIX["sources"][system + "_artifact"]["basis"]
        assert profile["actual_method"]["equation_of_time_applied"] is False
    bazi = next(row for row in bundle["profiles"].values() if row["system"] == "bazi")
    assert bazi["actual_method"]["day_sect"] == 2


def test_native_proposal_references_actual_bazi_values_without_persistence() -> None:
    proposed = source_root(MATRIX["sources"]["profile_proposal"])
    bundle = json_asset(CONTRACTS / "samples/skill-bindings/calculation-bundle.json")
    assert proposed["status"] == "calculation_proposal_not_persisted"
    assert proposed["writes"] == 0
    for branch in proposed["branches"]:
        for judgment in branch["judgments"]:
            artifact = bundle["artifacts"][judgment["artifact_id"]]
            assert judgment["value"] == resolved_values(artifact, [judgment["path"]])[0]
            assert (
                judgment["actual_method"]
                == bundle["profiles"][artifact["profile_id"]]["actual_method"]
            )


@pytest.mark.parametrize(
    "row", MATRIX["chapters"], ids=lambda row: row["system"] + "/" + row["topic"]
)
def test_chapter_text_version_and_content_hash_are_preserved(row: dict) -> None:
    loaded = SkillLibrary().load(row["system"], row["topic"])
    assert loaded["metadata"]["file"] == row["chapter_file"]
    assert "版本：" + row["chapter_version"] in loaded["text"]
    assert (
        hashlib.sha256(loaded["text"].encode("utf8")).hexdigest()
        == row["chapter_sha256"]
    )


@pytest.mark.parametrize("path", ["/data/yi/00", "/data/yi/-1", "/data/~2"])
def test_binding_resolution_does_not_accept_permissive_pointer_spellings(
    path: str,
) -> None:
    root = source_root(MATRIX["sources"]["almanac"])
    with pytest.raises((ValueError, KeyError)):
        resolved_values(root, [path])


def test_a_return_capability_cannot_silently_use_a_natal_artifact_root() -> None:
    natal = source_root(MATRIX["sources"]["astro_artifact"])
    key = ("astro", "returns", "conditional_fields", "solar_return")
    with pytest.raises((ValueError, KeyError)):
        resolved_values(natal, GROUPS[key][1])
    returned = source_root(MATRIX["sources"]["solar_return"])
    assert returned["technique"] == "solar_return"
    assert returned["data"]["root"]

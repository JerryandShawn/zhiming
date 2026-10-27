"""Educational data must remain complete, nonduplicative and honestly sourced."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "mingjing_core/knowledge/p8_glossary"
TERMS = json.loads((DIRECTORY / "terms_v1.json").read_text(encoding="utf8"))
SOURCES = json.loads((DIRECTORY / "sources_v1.json").read_text(encoding="utf8"))
REGISTRY = {row["source_id"]: row for row in SOURCES["sources"]}


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


@pytest.mark.parametrize(
    "filename,data",
    [("glossary.schema.json", TERMS), ("glossary_sources.schema.json", SOURCES)],
)
def test_data_and_source_registry_match_their_self_contained_schema(
    filename: str, data: dict
) -> None:
    schema = json.loads(
        (ROOT / "docs/v4/contracts" / filename).read_text(encoding="utf8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)


def test_declared_counts_are_actual_counts_and_complete_tag_cannot_hide_a_shortfall() -> (
    None
):
    assert TERMS["entry_count"] == len(TERMS["entries"])
    actual = dict(Counter(row["system"] for row in TERMS["entries"]))
    assert TERMS["system_counts"] == actual
    assert TERMS["source_registry_version"] == SOURCES["version"]
    if TERMS["stage"] == "draft_complete_200_for_review":
        assert len(TERMS["entries"]) >= 200
        assert TERMS["review_tag"] == "v1_ready_editorial_reviewed"
        for key, count in TERMS["planned_system_minimums"].items():
            assert actual[key] >= count
    else:
        assert "未" in "".join(TERMS["limits"])


def test_source_ids_and_term_ids_are_unique() -> None:
    assert len(REGISTRY) == len(SOURCES["sources"])
    assert len({row["term_id"] for row in TERMS["entries"]}) == len(TERMS["entries"])


def test_same_system_synonyms_do_not_count_as_extra_terms() -> None:
    seen = {}
    for term in TERMS["entries"]:
        for text in [term["term"], *term["aliases"]]:
            key = (term["system"], normalize(text))
            assert key not in seen or seen[key] == term["term_id"]
            seen[key] = term["term_id"]
    eight = next(
        row for row in TERMS["entries"] if row["term_id"] == "bazi-eight-characters"
    )
    assert "四柱" in eight["aliases"]
    assert not any(row["term"] == "四柱" for row in TERMS["entries"])


def test_definitions_and_examples_are_not_identical_fillers() -> None:
    rows = TERMS["entries"]
    for field in ("plain_explanation", "example"):
        values = [normalize(row[field]) for row in rows]
        assert len(values) == len(set(values))
    assert all(row["plain_explanation"] != row["example"] for row in rows)


@pytest.mark.parametrize("source", SOURCES["sources"], ids=lambda row: row["source_id"])
def test_local_source_paths_exist_without_crossing_the_repository(source: dict) -> None:
    assert source["locator"] and source["edition_page_status"]
    if source["path"]:
        path = (ROOT / source["path"]).resolve()
        assert path.is_relative_to(ROOT) and path.is_file()
        assert not path.is_relative_to(ROOT / "private")
    else:
        assert source["url"].startswith("https://")
    if source["kind"] == "project_editorial":
        assert "original_editorial" in source["verification_status"]


@pytest.mark.parametrize("term", TERMS["entries"], ids=lambda row: row["term_id"])
def test_every_term_has_resolvable_sources_scope_and_a_concrete_example(
    term: dict,
) -> None:
    assert term["term_id"].startswith(term["system"] + "-")
    assert len(term["plain_explanation"]) >= 20 and len(term["example"]) >= 15
    assert term["sources"] and term["school_differences"] and term["pending_review"]
    for reference in term["sources"]:
        assert reference["source_id"] in REGISTRY
        assert reference["locator"] and len(reference["support_scope"]) >= 10
    for difference in term["school_differences"]:
        assert len(difference["note"]) >= 12
        assert set(difference["source_ids"]) <= set(REGISTRY)
    assert "保证" not in term["plain_explanation"]
    assert "一定" not in term["plain_explanation"]


def test_tarot_major_sources_keep_project_authorship_and_exact_card_locators() -> None:
    deck = json.loads(
        (DIRECTORY.parent / "tarot_meanings.json").read_text(encoding="utf8")
    )
    known = {row["card_id"] for row in deck["cards"]}
    for term in TERMS["entries"]:
        for reference in term["sources"]:
            if reference["source_id"] != "project-tarot-editorial":
                continue
            if term["definition_kind"] == "editorial_symbol":
                match = re.search(r"card_id=(major-[0-9]{2})", reference["locator"])
                assert match and match.group(1) in known
            assert "原" in reference["support_scope"]
    assert REGISTRY["project-tarot-editorial"]["kind"] == "project_editorial"


def test_terms_are_not_a_fake_calculated_claim_registry() -> None:
    assert "不是" in TERMS["description"]
    assert "不能自动" in "".join(TERMS["limits"])
    for term in TERMS["entries"]:
        assert not {"claim_id", "rule_hits", "owner_user_id", "birth"}.intersection(
            term
        )


@pytest.mark.parametrize(
    "term_id,source_ids,locator_tokens",
    [
        ("bazi-year-pillar", {"p8-basis-pillars"}, ["getYearInGanZhiExact"]),
        ("bazi-month-pillar", {"p8-basis-pillars"}, ["getMonthInGanZhiExact"]),
        ("bazi-day-pillar", {"p8-basis-pillars"}, ["setSect(1)", "23:00"]),
        ("bazi-jie-boundary", {"p8-basis-pillars"}, ["physical"]),
        ("bazi-late-zi-hour", {"p8-basis-pillars"}, ["setSect(1)", "23:00"]),
        ("bazi-direct-officer", {"p8-pattern-review"}, ["restraint", "庚辛"]),
        (
            "bazi-yang-blade",
            {"p8-school-tables", "p8-named-methods"},
            ["/blade/", "named_stars", "source_status"],
        ),
        (
            "astro-orb",
            {"p8-astro-signs", "p8-synastry-default", "p8-daily-transit-default"},
            ["orb=6", "orb_degrees=6.0", "orb_degrees=2.0"],
        ),
    ],
)
def test_specific_method_claims_point_to_actual_implementation_or_tables(
    term_id: str, source_ids: set[str], locator_tokens: list[str]
) -> None:
    term = next(row for row in TERMS["entries"] if row["term_id"] == term_id)
    actual = {row["source_id"] for row in term["sources"]}
    assert source_ids <= actual
    locators = " ".join(row["locator"] for row in term["sources"])
    assert all(token in locators for token in locator_tokens)
    difference_sources = {
        name for row in term["school_differences"] for name in row["source_ids"]
    }
    assert source_ids <= difference_sources


def test_equal_houses_explains_exact_ascendant_and_unimplemented_option() -> None:
    term = next(
        row for row in TERMS["entries"] if row["term_id"] == "astro-equal-houses"
    )
    assert "Ascendant" in term["plain_explanation"]
    assert "每30度" in term["plain_explanation"]
    assert "当前未实现" in term["plain_explanation"]
    assert "金牛15度" in term["example"] and "金牛0度" in term["example"]

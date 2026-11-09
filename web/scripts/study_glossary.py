"""Plain-text, closed-field educational glossary projection; no user authority."""

from __future__ import annotations

import copy
import unicodedata
from collections import Counter
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from study_schema import require, validate

SYSTEMS = {"bazi": "八字", "ziwei": "紫微斗数", "astro": "西方占星", "tarot": "塔罗"}
MINIMUMS = {"bazi": 60, "ziwei": 55, "astro": 50, "tarot": 35}
SAFE_URLS = frozenset(
    (
        "https://gml.noaa.gov/grad/solcalc/calcdetails.html",
        "https://docs.iztro.com/posts/palace",
        "https://docs.iztro.com/learn/mutagen",
        "https://docs.iztro.com/learn/palace",
        "https://www.astro.com/swisseph/swephprg.htm",
    )
)
STAGES = frozenset(
    (
        "draft_seed_10_pending_root_review",
        "draft_in_progress_200_not_complete",
        "draft_complete_200_for_review",
    )
)


def plain(value: object, *, index_placeholder: bool = False) -> str:
    require(isinstance(value, str) and 0 < len(value.strip()) <= 16000)
    require(all(character.isprintable() or character in "\n\t" for character in value))
    # The audited tarot locator includes literal /cards/<index>/source. It is
    # source notation, never markup. No other tag or '<' is accepted anywhere.
    inspected = value.replace("<index>", "") if index_placeholder else value
    require("<" not in inspected)
    return value


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def repository_path(value: object, paths: set[str]) -> str:
    require(isinstance(value, str) and bool(value) and "\\" not in value)
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and "." not in value.split("/"))
    require(path.as_posix() == value and value in paths)
    require(value.startswith(("mingjing_core/", "hermes/")))
    return value


def project_sources(source: dict, schema: dict, paths: set[str]) -> dict:
    validate(source, schema)
    seen = set()
    for row in source["sources"]:
        ident = plain(row["source_id"])
        require(ident not in seen)
        seen.add(ident)
        for key in ("title", "kind", "verification_status", "edition_page_status"):
            plain(row[key])
        plain(row["locator"], index_placeholder=ident == "project-tarot-editorial")
        require(row["url"] is not None or row["path"] is not None)
        if row["url"] is not None:
            url = plain(row["url"])
            require(url in SAFE_URLS)
            parts = urlsplit(url)
            require(parts.scheme == "https" and not parts.username and not parts.password and not parts.fragment)
        if row["path"] is not None:
            repository_path(row["path"], paths)
    return copy.deepcopy(source)


def check_sources(term: dict, registered: set[str]) -> None:
    ids = []
    for item in term["sources"]:
        ident = plain(item["source_id"])
        require(ident in registered)
        ids.append(ident)
        plain(item["locator"])
        plain(item["support_scope"])
    require(len(ids) == len(set(ids)))
    for item in term["school_differences"]:
        plain(item["school"])
        plain(item["note"])
        require(len(item["source_ids"]) == len(set(item["source_ids"])))
        require(all(plain(ident) in registered for ident in item["source_ids"]))


def check_term(term: dict, registered: set[str], names: dict, identifiers: set[str], examples: set[str]) -> None:
    ident, system = term["term_id"], term["system"]
    require(system in SYSTEMS and ident.startswith(system + "-") and ident not in identifiers)
    identifiers.add(ident)
    for name in (term["term"], *term["aliases"]):
        label = (system, normalized(plain(name)))
        require(label not in names)
        names[label] = ident
    for key in ("definition_kind", "plain_explanation", "example"):
        plain(term[key])
    example = normalized(term["example"])
    require(example not in examples)
    examples.add(example)
    for text in term["pending_review"]:
        plain(text)
    check_sources(term, registered)


def check_counts(terms: dict) -> None:
    count = len(terms["entries"])
    actual = Counter(item["system"] for item in terms["entries"])
    require(type(terms["entry_count"]) is int and terms["entry_count"] == count)
    require(terms["system_counts"] == {key: actual[key] for key in SYSTEMS})
    require(all(type(value) is int for value in terms["system_counts"].values()))
    require(terms["systems"] == SYSTEMS and terms["planned_system_minimums"] == MINIMUMS)
    require(all(type(value) is int for value in terms["planned_system_minimums"].values()))
    stage = terms["stage"]
    require(stage in STAGES)
    if stage == "draft_seed_10_pending_root_review":
        require(count == 10 and "review_tag" not in terms)
    elif stage == "draft_in_progress_200_not_complete":
        require("review_tag" not in terms)
    else:
        require(count >= 200 and all(actual[key] >= minimum for key, minimum in MINIMUMS.items()))
        require(terms.get("review_tag") == "v1_ready_editorial_reviewed")


def project_glossary(
    terms: dict, sources: dict, terms_schema: dict, sources_schema: dict, repository_paths: set[str]
) -> tuple[dict, dict]:
    """Return independent public JSON values; never mutate the input datasets."""
    public_sources = project_sources(sources, sources_schema, repository_paths)
    validate(terms, terms_schema)
    require(terms["sources_file"] == "sources_v1.json")
    require(terms["source_registry_version"] == public_sources["version"])
    check_counts(terms)
    plain(terms["description"])
    for text in terms["limits"]:
        plain(text)
    registered = {row["source_id"] for row in public_sources["sources"]}
    names, identifiers, examples = {}, set(), set()
    for term in terms["entries"]:
        check_term(term, registered, names, identifiers, examples)
    return copy.deepcopy(terms), public_sources

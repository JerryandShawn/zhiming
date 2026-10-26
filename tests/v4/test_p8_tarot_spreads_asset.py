"""Readonly spread data maps actual runtime literals without changing any draws."""

from __future__ import annotations

import ast
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mingjing_core.adapters.charts.benchmarks.tarot_source_review import (
    review_service_source,
)

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "mingjing_core/knowledge/p8_tarot/spreads_v1.json"
DATA = json.loads(ASSET.read_text(encoding="utf8"))
SCHEMA = json.loads(
    (ROOT / "docs/v4/contracts/tarot_spreads.schema.json").read_text(encoding="utf8")
)
VALIDATOR = Draft202012Validator(SCHEMA)
DECK = ast.parse((ROOT / "hermes/tarot_deck.py").read_text(encoding="utf8"))
LITERALS = {
    target.id: ast.literal_eval(node.value)
    for node in DECK.body
    if isinstance(node, ast.Assign)
    for target in node.targets
    if isinstance(target, ast.Name)
    and target.id in {"SPREADS", "MAJOR", "MINOR", "SUITS", "RANK_CN"}
}
MEANINGS = json.loads((ROOT / DATA["meanings"]["path"]).read_text(encoding="utf8"))


def test_self_contained_strict_schema_and_actual_supported_counts() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    VALIDATOR.validate(DATA)
    assert DATA["runtime_supported_count"] == len(LITERALS["SPREADS"]) == 3
    assert DATA["supported_card_counts"] == [1, 3, 5]
    assert sum(row["card_count"] for row in DATA["spreads"]) == 9
    assert DATA["status"] == "readonly_handoff_not_runtime_registry"


@pytest.mark.parametrize("row", DATA["spreads"], ids=lambda row: row["id"])
def test_each_spread_is_an_exact_mapping_of_existing_runtime_metadata(
    row: dict,
) -> None:
    runtime = LITERALS["SPREADS"][row["id"]]
    assert {key: row[key] for key in runtime} == runtime
    assert row["card_count"] == len(runtime["positions"])
    assert row["runtime_supported"] is True
    assert row["purpose"] and row["when_to_use"] and len(row["limits"]) >= 3
    assert row["school_differences"][0]["status"].startswith("project_choice")
    assert row["options"]["required"] == (["A", "B"] if row["id"] == "choice5" else [])
    assert row["options"]["distinct_values"] is (row["id"] == "choice5")


@pytest.mark.parametrize(
    "spread_id,row",
    [
        (spread["id"], row)
        for spread in DATA["spreads"]
        for row in spread["position_guidance"]
    ],
    ids=lambda item: item if isinstance(item, str) else str(item["position"]),
)
def test_each_position_preserves_order_label_and_declares_original_limits(
    spread_id: str, row: dict
) -> None:
    assert (
        row["label"] == LITERALS["SPREADS"][spread_id]["positions"][row["position"] - 1]
    )
    assert row["focus"] and row["question"] and row["limit"]
    assert row["source_type"] == "original_editorial"
    assert row["source_refs"] == ["runtime-spreads", "p8-spread-guidance"]


@pytest.mark.parametrize("source", DATA["sources"], ids=lambda row: row["source_id"])
def test_sources_have_real_local_locators_and_lf_normalized_hashes(
    source: dict,
) -> None:
    path = (ROOT / source["path"]).resolve()
    assert path.is_relative_to(ROOT) and path.is_file() and source["locator"]
    if source["source_id"] == "p8-spread-guidance":
        assert "sha256" not in source and path == ASSET
        assert source["kind"] == "original_editorial"
    elif source["source_id"] == "runtime-service":
        review = review_service_source(path.read_text(encoding="utf8"))
        assert source["sha_mode"] == "utf8-lf-sha256"
        assert source["sha256"] == review["historical_lf_sha256"]
        assert review["complete_service_ast_unchanged"] is True
    else:
        assert source["sha_mode"] == "utf8-lf-sha256"
        assert (
            source["sha256"]
            == hashlib.sha256(
                path.read_text(encoding="utf8").encode("utf8")
            ).hexdigest()
        )


@pytest.mark.parametrize("card", MEANINGS["cards"], ids=lambda row: row["card_id"])
def test_each_of_78_original_meanings_is_unchanged_from_its_actual_legacy_literal(
    card: dict,
) -> None:
    if card["group"] == "major":
        original = LITERALS["MAJOR"][card["number"]]
        assert card["name"] == original[0] and card["name_en"] == original[1]
        texts = original[2:]
    else:
        texts = LITERALS["MINOR"][card["suit"]][card["number"] - 1]
        assert card["name"] == (
            LITERALS["SUITS"][card["suit"]][0] + LITERALS["RANK_CN"][card["number"] - 1]
        )
    assert (
        tuple(card[key] for key in ("upright", "reversed", "misreading", "question"))
        == texts
    )
    assert all(isinstance(value, str) and value.strip() for value in texts)
    assert card["source"]["type"] == "original_editorial"
    assert (
        card["source"]["version"]
        == card["meaning_version"]
        == MEANINGS["meaning_version"]
    )
    assert card["deck_version"] == MEANINGS["deck_version"]


def test_unique_78_cards_and_all_source_references_resolve_without_fake_aliases() -> (
    None
):
    cards = MEANINGS["cards"]
    assert len(cards) == len({row["card_id"] for row in cards}) == 78
    assert sum(row["group"] == "major" for row in cards) == 22
    assert all(
        sum(row.get("suit") == suit for row in cards) == 14
        for suit in LITERALS["SUITS"]
    )
    source_ids = {row["source_id"] for row in DATA["sources"]}
    for spread in DATA["spreads"]:
        assert set(spread["source_refs"]) <= source_ids
        for position in spread["position_guidance"]:
            assert set(position["source_refs"]) <= source_ids
    assert DATA["meanings"]["source_ref"] in source_ids
    assert DATA["reference_policy"]["static_aliases"] is False
    assert not any(
        token in ASSET.read_text(encoding="utf8")
        for token in ("〔t1〕", "〔c1〕", "〔r1〕")
    )


INVALID = [
    (["version"], "p8-tarot-spreads-v2"),
    (["runtime_supported_count"], 4),
    (["supported_card_counts"], [1, 3, 10]),
    (["spreads", 0, "id"], "celtic10"),
    (["spreads", 1, "id"], "focus1"),
    (["spreads", 0, "name"], "传统万能牌阵"),
    (["spreads", 0, "card_count"], True),
    (["spreads", 0, "runtime_supported"], False),
    (["spreads", 0, "positions"], ["未来结果"]),
    (["spreads", 1, "positions"], ["过去", "现在", "未来"]),
    (["spreads", 2, "options", "required"], []),
    (["spreads", 2, "options", "distinct_values"], False),
    (["spreads", 2, "options", "max_length"], 9999),
    (["spreads", 0, "position_guidance", 0, "position"], 0),
    (["spreads", 0, "position_guidance", 0, "label"], "未来结果"),
    (["spreads", 0, "position_guidance", 0, "question"], ""),
    (["spreads", 0, "position_guidance", 0, "limit"], ""),
    (["spreads", 0, "position_guidance", 0, "source_type"], "Waite_translation"),
    (["spreads", 0, "source_refs"], ["unknown-source"]),
    (["spreads", 0, "source_refs"], ["runtime-spreads", "runtime-spreads"]),
    (["sources", 1, "source_id"], "runtime-spreads"),
    (["sources", 0, "sha256"], "not-a-hash"),
    (["sources", 0, "sha_mode"], "raw-windows-bytes"),
    (["meanings", "source_type"], "classical_consensus"),
    (["meanings", "card_count"], 77),
    (["meanings", "meaning_version"], "unknown-version"),
    (["reference_policy", "static_aliases"], True),
    (["reference_policy", "runtime_alias_family"], "r"),
    (["spreads", 0, "extra"], "unregistered"),
    (["extra"], "unregistered"),
]


@pytest.mark.parametrize("path,value", INVALID, ids=lambda item: str(item))
def test_strict_schema_rejects_changed_runtime_semantics_or_false_provenance(
    path: list, value: object
) -> None:
    invalid = deepcopy(DATA)
    target = invalid
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert list(VALIDATOR.iter_errors(invalid))

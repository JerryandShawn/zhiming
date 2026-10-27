"""Independent completeness, integrity, fixed-policy and absent-evidence regressions."""

import copy
import json
import shutil
from pathlib import Path

import pytest

from tools.eval_material_v23.loader import ROOT, MaterialError, load_materials, read_json, validate_casebook
from tools.eval_material_v23.observe import evaluate_observation

CASES = load_materials()


def test_exact_fifty_two_original_plus_seven_space_cases() -> None:
    assert len(CASES) == 59
    assert len([case for case in CASES if case["source"] == "19"]) == 52
    assert [case["id"] for case in CASES if case["source"] == "P5b"] == [f"SP{i:02}" for i in range(1, 8)]
    assert sum(len(case["assertions"]) for case in CASES) == 189
    assert set(read_json(ROOT / "manifest.json")["sources"]) == {
        "19_新增评测场景.md",
        "18_提示词增补包/P5b_功能区与旧对话整理.md",
        "33_全量开发队列_本周.md",
        "25_P6评审难例与宽严样本.md",
    }


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_missing_real_observation_never_becomes_a_product_pass(case: dict) -> None:
    result = evaluate_observation(case)
    assert result.status in {"unverified", "blocked_decision", "blocked_dependency"}
    assert "not a product acceptance result" in result.evidence_scope


def test_frozen_rectification_and_missing_human_labels_are_not_filled_with_synthetic_passes() -> None:
    cases = {case["id"]: case for case in CASES}
    for case_id in ("RT05", "RT06", "RT07", "RT08", "RT10"):
        assert cases[case_id]["material_only"]
        assert cases[case_id]["availability"] == "blocked_dependency"
    assert cases["PR02"]["availability"] == "blocked_decision"
    for case_id in ("PR06", "J02"):
        assert cases[case_id]["availability"] == "blocked_dependency"
    assert "25号§16" in cases["J02"]["blocking_reasons"][0]
    assert "已提供" in cases["J02"]["blocking_reasons"][0]
    assert "尚缺" not in cases["J02"]["blocking_reasons"][0]
    assert cases["CR04"]["dataset_years"] == [2025]
    assert cases["J01"]["assertions"][-1]["expected"] == "record_only"


@pytest.mark.parametrize("name", ["scenarios.v23.yaml", "casebook.schema.json", "observation.schema.json"])
def test_manifest_detects_changes_before_loading_any_material(name: str, tmp_path: Path) -> None:
    for original in ROOT.iterdir():
        if original.name in {"manifest.json", "scenarios.v23.yaml", "casebook.schema.json", "observation.schema.json"}:
            shutil.copyfile(original, tmp_path / original.name)
    path = tmp_path / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(MaterialError, match="manifest_content_changed"):
        load_materials(tmp_path)


@pytest.mark.parametrize("case_id", ["RT05", "PR02", "PR06", "J02"])
def test_deleting_a_known_block_is_not_a_valid_contract_migration(case_id: str) -> None:
    book = read_json(ROOT / "scenarios.v23.yaml")
    case = next(case for case in book["cases"] if case["id"] == case_id)
    case.update(availability="ready_for_observation", blocking_reasons=[])
    with pytest.raises(MaterialError):
        validate_casebook(book, read_json(ROOT / "casebook.schema.json"))


def test_e2_scope_cannot_be_extended_to_2026_or_removed() -> None:
    for years in ([], [2026], [2025, 2026]):
        book = read_json(ROOT / "scenarios.v23.yaml")
        next(case for case in book["cases"] if case["id"] == "CR04")["dataset_years"] = years
        with pytest.raises(MaterialError, match="e2_2025_only_required"):
            validate_casebook(book, read_json(ROOT / "casebook.schema.json"))


@pytest.mark.parametrize("expected", [None, [], [None], [[""]], ["not-an-alternative-group"]])
def test_text_alternative_schema_rejects_empty_or_bad_expected_evidence(expected: object) -> None:
    book = read_json(ROOT / "scenarios.v23.yaml")
    first = book["cases"][0]["assertions"][1]
    assert first["operator"] == "text_all"
    first["expected"] = expected
    with pytest.raises(MaterialError):
        validate_casebook(book, read_json(ROOT / "casebook.schema.json"))


@pytest.mark.parametrize("change", ["duplicate-id", "unknown-field", "wrong-source", "duplicate-check"])
def test_strict_casebook_does_not_silently_ignore_material_shape_errors(change: str) -> None:
    book = read_json(ROOT / "scenarios.v23.yaml")
    if change == "duplicate-id":
        book["cases"][1]["id"] = book["cases"][0]["id"]
    elif change == "unknown-field":
        book["cases"][0]["reported_pass"] = True
    elif change == "wrong-source":
        book["cases"][0]["source"] = "P5b"
    else:
        book["cases"][0]["assertions"].append(copy.deepcopy(book["cases"][0]["assertions"][0]))
    with pytest.raises(MaterialError):
        validate_casebook(book, read_json(ROOT / "casebook.schema.json"))


@pytest.mark.parametrize("raw", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_yaml_subset_parser_does_not_allow_duplicate_keys_or_nonfinite_numbers(raw: str, tmp_path: Path) -> None:
    path = tmp_path / "unsafe.yaml"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(MaterialError):
        read_json(path)


def test_materials_are_json_compatible_yaml_with_stable_lf_and_no_empty_assertions() -> None:
    raw = (ROOT / "scenarios.v23.yaml").read_bytes()
    assert b"\r\n" not in raw
    assert json.loads(raw)["schema"] == "eval-material-casebook-v1"
    assert all(case["assertions"] for case in CASES)

"""Load only this isolated JSON-compatible YAML material set, with manifest integrity."""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
OPS = frozenset(
    {
        "eq",
        "text_all",
        "text_any",
        "text_none",
        "contains_all",
        "contains_any",
        "contains_none",
        "matches",
        "number_lte",
        "number_gte",
        "length_lte",
        "nonempty",
    }
)


class MaterialError(ValueError):
    """Only fixed codes are exposed, never an observation or conversation body."""


def require_json(value: object, depth: int = 0) -> None:
    if depth > 40:
        raise MaterialError("json_depth_exceeded")
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            require_json(item, depth + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            require_json(item, depth + 1)
        return
    raise MaterialError("strict_json_required")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise MaterialError("duplicate_json_key")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    def forbidden(value: str) -> None:
        raise MaterialError("nonfinite_json_number")

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs, parse_constant=forbidden)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise MaterialError("material_file_invalid") from None


def validate_casebook(value: object, schema: dict) -> None:
    require_json(value)
    errors = Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)
    if next(errors, None) is not None:
        raise MaterialError("casebook_schema_invalid")
    ids = [case["id"] for case in value["cases"]]
    expected = {
        f"{prefix}{index:02}"
        for prefix, start, end in (
            ("DC", 1, 4),
            ("TR", 1, 3),
            ("KU", 3, 6),
            ("AS", 1, 2),
            ("CL", 1, 5),
            ("FW", 1, 1),
            ("PR", 1, 6),
            ("RT", 1, 10),
            ("CR", 1, 6),
            ("J", 1, 5),
            ("K", 1, 6),
            ("SP", 1, 7),
        )
        for index in range(start, end + 1)
    }
    if len(ids) != 59 or set(ids) != expected:
        raise MaterialError("casebook_ids_invalid")
    for case in value["cases"]:
        if case["source"] != ("P5b" if case["id"].startswith("SP") else "19"):
            raise MaterialError("case_source_mismatch")
        if case["availability"] == "ready_for_observation" and case["blocking_reasons"]:
            raise MaterialError("ready_case_has_block")
        check_ids = [item["id"] for item in case["assertions"]]
        if len(check_ids) != len(set(check_ids)):
            raise MaterialError("assertion_id_duplicate")
        for item in case["assertions"]:
            _validate_expected(item)
    _fixed_policies({case["id"]: case for case in value["cases"]})


def _validate_expected(item: dict) -> None:
    operator, expected = item["operator"], item["expected"]
    if operator not in OPS or expected is None:
        raise MaterialError("assertion_expected_invalid")
    if operator in {"text_all", "text_any", "text_none", "contains_all", "contains_any", "contains_none"} and (
        not isinstance(expected, list) or not expected
    ):
        raise MaterialError("assertion_expected_list_required")
    if operator in {"number_lte", "number_gte", "length_lte"} and type(expected) not in {int, float}:
        raise MaterialError("assertion_expected_number_required")
    if operator == "length_lte" and (type(expected) is not int or expected < 0):
        raise MaterialError("assertion_expected_length_required")
    if operator == "text_all" and any(
        not isinstance(group, list) or not group or any(type(word) is not str or not word.strip() for word in group)
        for group in expected
    ):
        raise MaterialError("assertion_alternatives_invalid")
    if operator in {"text_any", "text_none"} and any(type(word) is not str or not word.strip() for word in expected):
        raise MaterialError("assertion_words_invalid")
    if operator == "nonempty" and expected is not True:
        raise MaterialError("assertion_nonempty_expected_true")
    if operator == "matches" and (type(expected) is not str or not expected):
        raise MaterialError("assertion_pattern_required")
    if operator == "matches":
        try:
            re.compile(expected)
        except re.error:
            raise MaterialError("assertion_pattern_invalid") from None


def _fixed_policies(cases: dict[str, dict]) -> None:
    for case_id in ("RT05", "RT06", "RT07", "RT08", "RT10"):
        if not cases[case_id]["material_only"] or cases[case_id]["availability"] != "blocked_dependency":
            raise MaterialError("rectification_material_only_required")
    for case_id, status in (
        ("PR02", "blocked_decision"),
        ("PR06", "blocked_dependency"),
        ("J02", "blocked_dependency"),
    ):
        if cases[case_id]["availability"] != status or not cases[case_id]["blocking_reasons"]:
            raise MaterialError("fixed_block_missing")
    cr04 = cases["CR04"]
    if cr04["dataset_years"] != [2025] or not any(
        check["path"] == "report.dataset_years" and check["operator"] == "eq" and check["expected"] == [2025]
        for check in cr04["assertions"]
    ):
        raise MaterialError("e2_2025_only_required")


def load_materials(root: Path = ROOT) -> tuple[dict, ...]:
    manifest = read_json(root / "manifest.json")
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schema", "contract", "serialization", "case_count", "files", "sources", "limits"}
        or manifest["schema"] != "eval-material-manifest-v1"
        or manifest["case_count"] != 59
    ):
        raise MaterialError("manifest_shape_invalid")
    expected_files = {"scenarios.v23.yaml", "casebook.schema.json", "observation.schema.json"}
    if manifest["contract"] != "deterministic-eval-v2.3.0-candidate-material-v1" or (
        manifest["serialization"] != "json-compatible-yaml-1.2"
    ):
        raise MaterialError("manifest_contract_invalid")
    expected_sources = {
        "19_新增评测场景.md",
        "18_提示词增补包/P5b_功能区与旧对话整理.md",
        "33_全量开发队列_本周.md",
        "25_P6评审难例与宽严样本.md",
    }
    if (
        not isinstance(manifest["sources"], dict)
        or set(manifest["sources"]) != expected_sources
        or any(
            type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None
            for value in manifest["sources"].values()
        )
    ):
        raise MaterialError("manifest_source_hash_invalid")
    if not isinstance(manifest["files"], dict) or set(manifest["files"]) != expected_files:
        raise MaterialError("manifest_members_invalid")
    for name, expected_hash in manifest["files"].items():
        try:
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        except OSError:
            raise MaterialError("manifest_file_unavailable") from None
        if actual != expected_hash:
            raise MaterialError("manifest_content_changed")
    value = read_json(root / "scenarios.v23.yaml")
    validate_casebook(value, read_json(root / "casebook.schema.json"))
    return tuple(value["cases"])

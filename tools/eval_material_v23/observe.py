"""Predicate checks over supplied offline observations, never product execution or authorization."""

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .loader import ROOT, MaterialError, load_materials, read_json, require_json


@dataclass(frozen=True)
class AssertionResult:
    id: str
    status: str
    reason: str


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    status: str
    assertions: tuple[AssertionResult, ...]
    evidence_scope: str = "supplied offline observations only; not a product acceptance result"


@lru_cache(maxsize=1)
def _case_registry() -> MappingProxyType:
    return MappingProxyType(
        {case["id"]: json.dumps(case, ensure_ascii=False, sort_keys=True) for case in load_materials()}
    )


def evaluate_observation(case: dict, observation: dict | None = None) -> CaseEvaluation:
    require_json(case)
    if (
        type(case) is not dict
        or type(case.get("id")) is not str
        or (json.dumps(case, ensure_ascii=False, sort_keys=True) != _case_registry().get(case["id"]))
    ):
        raise MaterialError("case_not_bound_to_loaded_material")
    blocked = case["availability"]
    if blocked in {"blocked_decision", "blocked_dependency"}:
        return CaseEvaluation(case["id"], blocked, ())
    if observation is None:
        return CaseEvaluation(case["id"], "unverified", ())
    require_json(observation)
    schema = read_json(ROOT / "observation.schema.json")
    if next(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(observation), None) is not None:
        raise MaterialError("observation_schema_invalid")
    if observation["case_id"] != case["id"] or observation["scope"] != case["scope"]:
        raise MaterialError("observation_case_scope_mismatch")
    instant = datetime.fromisoformat(observation["observed_at"].replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise MaterialError("observation_time_must_be_aware")
    evidence = {item["path"]: item for item in observation["evidence"]}
    if len(evidence) != len(observation["evidence"]):
        raise MaterialError("observation_duplicate_path")
    if set(evidence) - {item["path"] for item in case["assertions"]}:
        raise MaterialError("observation_unknown_path")
    results = tuple(_one(item, evidence.get(item["path"])) for item in case["assertions"])
    status = (
        "failed"
        if any(item.status == "failed" for item in results)
        else ("unverified" if any(item.status == "unverified" for item in results) else "observed_pass")
    )
    return CaseEvaluation(case["id"], status, results)


def _one(assertion: dict, evidence: dict | None) -> AssertionResult:
    if evidence is None or evidence["kind"] != assertion["kind"] or evidence["value"] is None:
        return AssertionResult(assertion["id"], "unverified", "missing_typed_evidence")
    value = evidence["value"]
    if isinstance(value, str) and not value.strip():
        return AssertionResult(assertion["id"], "unverified", "empty_evidence")
    result = _check(assertion["operator"], value, assertion["expected"])
    return AssertionResult(assertion["id"], "passed" if result else "failed", "predicate_result")


def _exact(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_exact(a, b) for a, b in zip(left, right, strict=True))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_exact(value, right[key]) for key, value in left.items())
    return left == right


def _positive(text: str, expected: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    needle = re.sub(r"\s+", "", expected)
    if not needle:
        return False
    pattern = re.escape(needle)
    if needle[0].isdigit():
        pattern = r"(?<![0-9])" + pattern
    if needle[-1].isdigit():
        pattern += r"(?![0-9])"
    for match in re.finditer(pattern, compact):
        prefix = compact[max(0, match.start() - 8) : match.start()]
        if re.search(r"(?:不是|并非|不等于|不能说|没有|未满|并没有|not|never)[，,:：]*$", prefix, re.I) is None:
            return True
    return False


def _check(operator: str, value: Any, expected: Any) -> bool:
    if operator == "eq":
        return _exact(value, expected)
    if operator.startswith("text_"):
        if type(value) is not str:
            return False
        groups = expected if operator == "text_all" else [expected]
        if operator == "text_none":
            return not any(_positive(value, item) for item in expected)
        return all(any(_positive(value, item) for item in group) for group in groups)
    if operator.startswith("contains_"):
        if not isinstance(value, list):
            return False
        matched = [any(_exact(item, candidate) for candidate in value) for item in expected]
        return (
            all(matched)
            if operator == "contains_all"
            else not any(matched)
            if operator == "contains_none"
            else any(matched)
        )
    if operator == "matches":
        return type(value) is str and re.search(expected, value) is not None
    if operator in {"number_lte", "number_gte"}:
        if type(value) not in {int, float} or (type(value) is float and not math.isfinite(value)):
            return False
        return value <= expected if operator == "number_lte" else value >= expected
    if operator == "length_lte":
        return isinstance(value, (str, list)) and len(value) <= expected
    if operator == "nonempty":
        return isinstance(value, (str, list, dict)) and bool(value)
    raise MaterialError("assertion_operator_invalid")

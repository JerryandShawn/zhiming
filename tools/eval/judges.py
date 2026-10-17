"""Deterministic assertion checks and the separately metered live critic."""

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.eval.targets.base import TurnResult


@dataclass(frozen=True)
class AssertionResult:
    name: str
    passed: bool


def _alternatives(text: str) -> list[str]:
    return [part for part in text.split("|") if part]


def _includes(text: str, pattern: str) -> bool:
    return any(part in text for part in _alternatives(pattern))


def _path(value: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _matches(row: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(_path(row, key) == value for key, value in expected.items())


def _receipt_check(expected: str | dict[str, Any], receipts: list[dict[str, Any]]) -> bool:
    if isinstance(expected, str):
        return any(row.get("status") == expected for row in receipts)
    return any(_matches(row, expected) for row in receipts)


def _db_check(expected: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    if "path" in expected:
        actual = _path(snapshot, expected["path"])
        if "equals" in expected:
            return actual == expected["equals"]
        if "contains" in expected:
            return isinstance(actual, str | list | dict) and expected["contains"] in actual
        if "lte" in expected or "gte" in expected:
            if isinstance(actual, bool) or not isinstance(actual, int | float) or not math.isfinite(actual):
                return False
            return expected.get("gte", -math.inf) <= actual <= expected.get("lte", math.inf)
        return actual is None if expected.get("absent", False) else actual is not None
    rows = snapshot.get(expected.get("table", "entities"), [])
    if not isinstance(rows, list):
        return False
    selector = {key: value for key, value in expected.items() if key in {"kind", "id", "status"}}
    selector.update(expected.get("where", {}))
    matched = [row for row in rows if isinstance(row, dict) and _matches(row, selector)]
    if "count" in expected:
        return len(matched) == expected["count"]
    return not matched if expected.get("absent", False) else bool(matched)


def _event_check(expected: list[Any], actual: list[str]) -> bool:
    names = [item if isinstance(item, str) else item["type"] for item in expected]
    cursor = iter(actual)
    return all(any(observed == wanted for observed in cursor) for wanted in names)


def check_assertions(expect: dict[str, Any], result: TurnResult) -> list[AssertionResult]:
    """Each check has a stable name; failure diagnostics never contain text."""
    checks: list[AssertionResult] = []
    if expect.get("must_include_any"):
        passed = any(_includes(result.text, value) for value in expect["must_include_any"])
        checks.append(AssertionResult("must_include_any", passed))
    for name, predicate in (
        ("must_include_all", lambda value: _includes(result.text, value)),
        ("must_not_include", lambda value: not _includes(result.text, value)),
        ("tools_called", lambda value: value in result.tools_called),
        ("tools_not_called", lambda value: value not in result.tools_called),
        ("receipts", lambda value: _receipt_check(value, result.receipts)),
        ("db", lambda value: _db_check(value, result.db)),
    ):
        for index, value in enumerate(expect.get(name, []), 1):
            checks.append(AssertionResult(f"{name}[{index}]", bool(predicate(value))))
    if "events" in expect and expect["events"] is not None:
        checks.append(AssertionResult("events", _event_check(expect["events"], result.events)))
    questions = result.text.count("？") + result.text.count("?")
    for name, passed in (
        ("min_questions", questions >= expect.get("min_questions", 0)),
        ("max_questions", questions <= expect.get("max_questions", questions)),
    ):
        if name in expect:
            checks.append(AssertionResult(name, passed))
    if result.error:
        checks.append(AssertionResult("target_error", False))
    return checks


JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score", "verdict", "issues"],
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "verdict": {"type": "string", "enum": ["pass", "revise"]},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "severity"],
                "properties": {
                    "type": {"type": "string"},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                },
            },
        },
    },
}


class ModelJudge:
    """Reuse the v3 configured model; P0 introduces no model adapter layer."""

    def __init__(self, model: str, rubric: Path, provider: Any = None) -> None:
        if provider is None:
            from mingjing_core.adapters.model import ConfiguredModel

            provider = ConfiguredModel(model=model)
        self.provider = provider
        self.rubric = rubric.read_text(encoding="utf-8")

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        try:
            response = self.provider.generate(
                system=self.rubric,
                payload=payload,
                schema=JUDGE_SCHEMA,
                purpose="eval_critic",
            )
            output = response["output"]
            score = output["score"]
            if isinstance(score, bool) or not isinstance(score, int | float) or not math.isfinite(score):
                raise ValueError("invalid critic score")
            if not 0 <= score <= 1 or output["verdict"] not in {"pass", "revise"}:
                raise ValueError("invalid critic verdict")
            if not isinstance(output["issues"], list):
                raise ValueError("invalid critic issues")
            for issue in output["issues"]:
                if not isinstance(issue, dict) or not isinstance(issue.get("type"), str):
                    raise ValueError("invalid critic issue")
                if type(issue.get("severity")) is not int or not 1 <= issue["severity"] <= 5:
                    raise ValueError("invalid critic severity")
            severe = max((issue["severity"] for issue in output["issues"]), default=0)
            if severe >= 5 and score > 0.2:
                raise ValueError("critic score conflicts with severity")
            if (severe >= 3) != (output["verdict"] == "revise"):
                raise ValueError("critic verdict conflicts with issues")
            if output["verdict"] == "revise" and score == 1:
                raise ValueError("critic score conflicts with verdict")
            return {
                "score": float(score),
                "model_calls": 1,
                "elapsed_seconds": response.get("latency_seconds", time.monotonic() - started),
                "error": None,
            }
        except Exception as exc:
            return {
                "score": 0.0,
                "model_calls": 1,
                "elapsed_seconds": time.monotonic() - started,
                "error": type(exc).__name__,
            }

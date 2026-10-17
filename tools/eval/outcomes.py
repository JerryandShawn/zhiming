"""Separate unavailable infrastructure from observed business capability failures."""

from typing import Any


def is_infrastructure_failure(case: dict[str, Any]) -> bool:
    if case.get("stop_reason"):
        return True
    if case.get("error_code") or case.get("judge_error_code"):
        return True
    return bool(case.get("target_error_code") and case.get("error_category") != "business")

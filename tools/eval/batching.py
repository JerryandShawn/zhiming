"""Bounded sequential batches with actual-call accounting across explicit resumes."""

import time
from collections.abc import Callable
from typing import Any

from tools.eval.outcomes import is_infrastructure_failure
from tools.eval.schema import Scenario

USAGE_KEYS = (
    "model_calls",
    "target_model_calls",
    "judge_model_calls",
    "target_model_elapsed_seconds",
    "judge_model_elapsed_seconds",
    "elapsed_seconds",
)


def _usage() -> dict[str, int | float]:
    return dict.fromkeys(USAGE_KEYS, 0)


def _account(batch: dict[str, Any], case: dict[str, Any], reused: bool) -> None:
    kind = "inherited_usage" if reused else "new_usage"
    batch["cached_ids" if reused else "executed_ids"].append(case["id"])
    for key in USAGE_KEYS:
        batch[kind][key] += case.get(key, 0)


def _usage_metadata(report: dict[str, Any], attempt: int) -> None:
    current = [batch for batch in report["batches"] if batch["attempt"] == attempt]
    usage = {name: _usage() for name in ("new_usage", "inherited_usage", "historical_actual_usage")}
    for batch in current:
        for name in ("new_usage", "inherited_usage"):
            for key in USAGE_KEYS:
                usage[name][key] += batch[name][key]
    for batch in report["batches"]:
        for key in USAGE_KEYS:
            usage["historical_actual_usage"][key] += batch["new_usage"][key]
    report["metadata"]["execution_usage"] = usage


def run_batches(
    scenarios: list[Scenario],
    report: dict[str, Any],
    observe: Callable[[Scenario], tuple[dict[str, Any], bool]],
    publish: Callable[[], None],
    *,
    batch_size: int = 10,
) -> None:
    if not 1 <= batch_size <= 10:
        raise ValueError("Evaluation batch size must be between 1 and 10")
    attempt = max((batch["attempt"] for batch in report["batches"]), default=0) + 1
    report["metadata"].update(batch_size=batch_size, attempt=attempt)
    known = {case["id"]: case for case in report["cases"]}
    for offset in range(0, len(scenarios), batch_size):
        batch = {
            "attempt": attempt,
            "batch": offset // batch_size + 1,
            "scenario_ids": [scenario.id for scenario in scenarios[offset : offset + batch_size]],
            "executed_ids": [],
            "cached_ids": [],
            "new_usage": _usage(),
            "inherited_usage": _usage(),
            "status": "running",
        }
        report["batches"].append(batch)
        _run_batch(scenarios, offset, batch_size, batch, known, report, observe, publish)
        _usage_metadata(report, attempt)
        publish()
        if report["metadata"].get("stop_reason"):
            break
    report["metadata"]["pending_scenario_ids"] = [scenario.id for scenario in scenarios if scenario.id not in known]


def _run_batch(
    scenarios: list[Scenario],
    offset: int,
    size: int,
    batch: dict[str, Any],
    known: dict[str, dict[str, Any]],
    report: dict[str, Any],
    observe: Callable[[Scenario], tuple[dict[str, Any], bool]],
    publish: Callable[[], None],
) -> None:
    started = time.perf_counter()
    for scenario in scenarios[offset : offset + size]:
        case, reused = observe(scenario)
        known[scenario.id] = case
        _account(batch, case, reused)
        report["cases"] = [known[item.id] for item in scenarios if item.id in known]
        _usage_metadata(report, batch["attempt"])
        publish()
        print(f"{scenario.id}: {case['status']} score={case['score']}", flush=True)
        if case.get("stop_reason"):
            report["metadata"].update(
                status="incomplete",
                stop_reason=case["stop_reason"],
                stop_role=case["stop_role"],
                requires_user_decision=True,
            )
            break
    batch["wall_seconds"] = round(time.perf_counter() - started, 3)
    batch["status"] = "stopped" if report["metadata"].get("stop_reason") else "complete"
    if batch["status"] == "complete" and any(is_infrastructure_failure(known[item]) for item in batch["executed_ids"]):
        batch["status"] = "incomplete"

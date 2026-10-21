"""Derive execution-only overlays while preserving the 47 scoring contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import Scenario, load_scenarios

REQUIRED_IDS = frozenset(
    [f"T{i:02}" for i in range(1, 15)]
    + [f"M{i:02}" for i in (1, 2, 3, 4, 9, 10, 11, 13)]
    + [f"R{i:02}" for i in range(1, 10)]
    + [f"Q{i:02}" for i in range(1, 8)]
    + ["TA01", "TA02", "TA03", "D01", "S01", "X03", "X04", "X05", "L01"]
)


def execution_overlay(scenario: Scenario) -> Scenario:
    data = scenario.model_dump(mode="json", exclude_none=True)
    for step in data["scripted"]:
        actions = []
        for action in step["model"]:
            action = {key: deepcopy(value) for key, value in action.items() if key in {"text", "tool_call"}}
            if action:
                actions.append(action)
        step["model"] = actions
        for action in actions:
            call = action.get("tool_call", {})
            args: dict[str, Any] = call.get("arguments", {})
            if call.get("name") == "schedule_followup":
                prior = next(
                    (
                        a["tool_call"]["arguments"]
                        for a in actions
                        if a.get("tool_call", {}).get("name") == "memory_write"
                    ),
                    None,
                )
                args.update(
                    message_id=f"turn-{step['turn']}",
                    quote=prior["quote"] if prior else data["turns"][step["turn"] - 1]["user"],
                )
                if args.get("source_fact_id"):
                    args["source_fact_id"] = "$last_receipt.id"
            if call.get("name") == "tarot_start":
                args.update(message_id=f"turn-{step['turn']}", draw_source="pick")
                original = data["turns"][step["turn"] - 1]["user"]
                if args["question"] not in original:
                    args["question"] = original
    result = Scenario.model_validate(data)
    if scenario_contract_hash(result) != scenario_contract_hash(scenario):
        raise ValueError("Execution overlay changed the scoring contract")
    return result


def write_corpus(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    cases = [case for case in load_scenarios(source) if case.id in REQUIRED_IDS]
    if {case.id for case in cases} != REQUIRED_IDS:
        raise ValueError("P3 corpus is incomplete")
    for case in cases:
        data = execution_overlay(case).model_dump(mode="json", exclude_defaults=True, exclude_none=True)
        path = destination / (case.id + ".yaml")
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    write_corpus(root / "scenarios", root / "scenarios_v4")

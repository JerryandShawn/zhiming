"""Isolated final-batch material replay; no live target or business execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, model_validator

from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario
from tools.eval.targets.fake_target import FakeTarget

ROOT = Path(__file__).resolve().parents[4]
DIRECTORY = ROOT / "docs/v4/contracts/final_prep_20261027"
CATEGORIES = {
    **dict.fromkeys(("S01", "S02", "S03", "S04", "K04"), "safety"),
    **dict.fromkeys(("M01", "M03", "M05", "M08", "KU03"), "memory_write"),
    **dict.fromkeys(("R02", "KU04"), "memory_recall"),
    "F01": "forget",
    "TA01": "tarot",
    "T13": "time",
    **dict.fromkeys(("P02", "PR01", "PR03"), "proactive"),
    **dict.fromkeys(("J03", "J04", "J05", "X04", "X08"), "robustness"),
    **dict.fromkeys(
        ("P8DT01", "P8WS01", "P8AL01", "P8SY01", "P8BA01", "CR01"), "chart"
    ),
}


class FinalScenario(Scenario):
    """Same strict fields; override only this isolated allowlist and its mapping."""

    id: Annotated[str, Field(pattern="^(?:" + "|".join(CATEGORIES) + ")$")]

    @model_validator(mode="after")
    def replay_is_complete(self) -> FinalScenario:
        if self.category != CATEGORIES[self.id] or "v4" not in self.targets:
            raise ValueError("final_material_category_or_target_invalid")
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("final_material_targets_duplicate")
        if sorted(step.turn for step in self.scripted) != list(
            range(1, len(self.turns) + 1)
        ):
            raise ValueError("final_material_replay_incomplete")
        return self


def load_final_cases(directory: Path = DIRECTORY) -> list[FinalScenario]:
    paths = sorted((directory / "scenarios").glob("*.yaml"))
    rows = [FinalScenario.model_validate(yaml.safe_load(p.read_bytes())) for p in paths]
    if len(rows) != 29 or {row.id for row in rows} != set(CATEGORIES):
        raise ValueError("final_material_exact_29_required")
    if sum(row.category == "safety" for row in rows) != 5:
        raise ValueError("final_material_exact_5_safety_required")
    return rows


def replay() -> dict:
    results = []
    for scenario in load_final_cases():
        target = FakeTarget()
        try:
            results.append(evaluate_scenario(scenario, target))
        finally:
            target.close()
    return {
        "mode": "scripted_fake_material_only",
        "passed": sum(row["status"] == "passed" for row in results),
        "count": len(results),
        "real_model_calls": 0,
        "business_tools_executed": 0,
        "real_agent_gate": "not_run",
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["scripted"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite evidence")
    result = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(
        (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
    )
    print({key: result[key] for key in ("passed", "count", "real_model_calls")})
    raise SystemExit(result["passed"] != result["count"])


if __name__ == "__main__":
    main()

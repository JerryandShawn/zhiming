"""Replay new acceptance material with the existing fake target; never a live gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.eval.contracts import scenario_contract_hash
from tools.eval.engine import evaluate_scenario
from tools.eval.targets.fake_target import FakeTarget

from .acceptance_scenarios import load_p8_scenarios


def replay() -> dict:
    rows = []
    for scenario in load_p8_scenarios():
        target = FakeTarget()
        try:
            row = evaluate_scenario(scenario, target)
            row["scenario_contract_sha256"] = scenario_contract_hash(scenario)
            rows.append(row)
        finally:
            target.close()
    return {
        "mode": "scripted_fake_material_replay",
        "cases": rows,
        "passed": sum(row["status"] == "passed" for row in rows),
        "count": len(rows),
        "real_model_calls": 0,
        "business_tools_executed": 0,
        "agent_runtime_gate": "not_run; mainline owns real target and seed/observer mapping",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["scripted"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to replace an existing evidence file")
    result = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    print(
        json.dumps(
            {key: result[key] for key in ("passed", "count", "real_model_calls")}
        )
    )
    raise SystemExit(result["passed"] != result["count"])


if __name__ == "__main__":
    main()

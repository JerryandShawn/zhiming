"""Private judge context resolved from the same fixtures and native committed turns."""

from copy import deepcopy
from typing import Any
from tools.eval.schema import Scenario
from tools.eval.targets.base import TurnResult

from tools.eval.targets.v3_seed import V3Seeder


def judge_payload(scenario: Scenario, index: int, result: TurnResult) -> dict[str, Any]:
    turn = scenario.turns[index - 1]
    seed = scenario.seed.model_dump(mode="json")
    profile = V3Seeder.load_profile(seed)
    return {
        "scenario_id": scenario.id,
        "user": turn.user,
        "clock": turn.at or scenario.clock,
        "seed": seed,
        "resolved_profile": {
            key: deepcopy(profile[key]) for key in ("name", "occupation", "goals", "birth") if key in profile
        },
        "seed_memories": deepcopy(seed.get("facts", [])),
        "prior_turns": deepcopy(result.metadata.get("prior_turns", [])),
        "tool_effects": deepcopy(result.metadata.get("tool_effects", {})),
        "receipts": result.receipts,
        "tools_called": result.tools_called,
        "criterion": turn.expect.judge,
        "answer": result.text,
    }

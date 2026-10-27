"""Additive P8 namespace using the existing strict scenario fields and assertions."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, model_validator

from tools.eval.schema import Scenario

ROOT = Path(__file__).resolve().parents[4]
SCENARIOS = ROOT / "docs/v4/contracts/p8_acceptance_20261027/scenarios"
P8_ID = r"^P8(?:DT0[1-3]|WS0[1-3]|AL0[1-3]|SY0[1-3]|BA01)$"


class P8Scenario(Scenario):
    """Only the new namespace/category rule changes; base fields remain strict."""

    id: Annotated[str, Field(pattern=P8_ID)]

    @model_validator(mode="after")
    def replay_is_complete(self) -> P8Scenario:
        if self.category != "chart" or self.targets != ["v4"]:
            raise ValueError("P8 scenarios require chart category and only v4 target")
        if sorted(step.turn for step in self.scripted) != list(
            range(1, len(self.turns) + 1)
        ):
            raise ValueError("Exactly one scripted step is required for every turn")
        return self


def load_p8_scenarios(directory: Path = SCENARIOS) -> list[P8Scenario]:
    scenarios = [
        P8Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf8")))
        for path in sorted(directory.glob("*.yaml"))
    ]
    if not scenarios or len({row.id for row in scenarios}) != len(scenarios):
        raise ValueError("P8 scenarios must be nonempty with unique IDs")
    return scenarios

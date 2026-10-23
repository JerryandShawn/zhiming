"""Execution-only argument adaptation cannot alter scoring or infer ambiguous targets."""

from copy import deepcopy
from pathlib import Path

import pytest

from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_memory_script_args import adapt_memory_script_args


def original() -> dict:
    case = next(c for c in load_scenarios(Path("tools/eval/scenarios")) if c.id == "F02")
    return case.model_dump(mode="json", exclude_none=True)


def test_argument_adapter_changes_only_model_script_and_keeps_actual_selected_source() -> None:
    case = next(c for c in load_scenarios(Path("tools/eval/scenarios")) if c.id == "F02")
    executable = execution_overlay(case)
    assert scenario_contract_hash(case) == scenario_contract_hash(executable)
    assert executable.scripted[0].model[0].tool_call.arguments == {"message_id": "turn-1", "fact_id": "anxiety"}
    assert executable.turns == case.turns and executable.seed == case.seed


@pytest.mark.parametrize("change", ["ambiguous", "missing", "scope", "empty"])
def test_legacy_script_cannot_guess_a_target_from_an_invalid_query(change: str) -> None:
    data = original()
    args = data["scripted"][0]["model"][0]["tool_call"]["arguments"]
    if change == "ambiguous":
        data["seed"]["facts"].append(dict(deepcopy(data["seed"]["facts"][0]), id="other"))
    elif change == "missing":
        data["seed"]["facts"] = []
    elif change == "scope":
        args["scope"] = "any_owner"
    else:
        args["query"] = ""
    with pytest.raises(ValueError):
        adapt_memory_script_args(data)

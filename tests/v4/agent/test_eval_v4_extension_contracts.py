"""The additional corpus has its own contracts and cannot replace mandatory gold."""

from pathlib import Path

from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import REQUIRED_IDS

ROOT = Path(__file__).resolve().parents[3] / "tools/eval"


def test_extension_contracts_are_separate_and_observe_real_db_outputs() -> None:
    required = load_scenarios(ROOT / "scenarios_v4")
    extra = load_scenarios(ROOT / "scenarios_v4_extensions")
    assert {case.id for case in required} == REQUIRED_IDS and len(required) == 48
    assert {case.id for case in extra} == {
        "T01",
        "T02",
        "T08",
        "R02",
        "R03",
        "R07",
        "Q01",
        "Q03",
        "Q06",
        "S01",
        "S02",
        "S03",
        "X07",
    }
    originals = {case.id: case for case in required}
    for case in extra:
        assert any(turn.expect.db for turn in case.turns)
        assert all(
            set(action.model_dump(exclude_none=True)) <= {"text", "tool_call"}
            for step in case.scripted
            for action in step.model
        )
        if case.id in originals:
            assert scenario_contract_hash(case) != scenario_contract_hash(originals[case.id])

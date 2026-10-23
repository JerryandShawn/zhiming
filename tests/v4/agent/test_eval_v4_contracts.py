"""P3 execution overlays preserve the frozen measurement assertions and seeds."""

from pathlib import Path

import pytest

from tools.eval.contracts import scenario_contract_hash
from tools.eval.runner import main, parser
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import REQUIRED_IDS

ROOT = Path(__file__).resolve().parents[3]


def test_all_47_execution_overlays_preserve_original_scoring_contracts() -> None:
    frozen = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios")}
    overlays = load_scenarios(ROOT / "tools/eval/scenarios_v4")
    assert {case.id for case in overlays} == REQUIRED_IDS and len(REQUIRED_IDS) == 47
    for case in overlays:
        assert scenario_contract_hash(case) == scenario_contract_hash(frozen[case.id])
        assert all(
            set(action.model_dump(exclude_none=True)) <= {"text", "tool_call"}
            for step in case.scripted
            for action in step.model
        )


def test_v4_cli_is_offline_only_and_default_fake_is_unchanged() -> None:
    assert parser().parse_args([]).target is None
    with pytest.raises(SystemExit, match="Supported modes"):
        main(["--target", "v4", "--mode", "live"])
    assert main(["--target", "v4", "--validate-only"]) == 0

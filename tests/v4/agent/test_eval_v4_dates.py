"""Isolated 19-date scenarios keep model scripts separate from product observations."""

from pathlib import Path

from tools.eval.schema import load_scenarios


def test_seven_date_cases_use_real_tools_and_assert_actual_context_or_persisted_output() -> None:
    root = Path(__file__).resolve().parents[3] / "tools/eval/scenarios_v4_dates"
    cases = load_scenarios(root)
    assert {case.id for case in cases} == {"DC01", "DC02", "DC03", "DC04", "TR01", "TR02", "TR03"}
    for case in cases:
        assert case.targets == ["v4"] and case.turns[0].expect.db
        assert not any("parser" in key.lower() for key in case.seed.controls)
        for action in case.scripted[0].model:
            assert action.db is None and action.receipt is None and action.result is None and action.meta is None

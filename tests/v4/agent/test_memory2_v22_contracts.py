"""Appendix B is isolated; widening its ID registry cannot change old scoring hashes."""

from __future__ import annotations

import json
from pathlib import Path

from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import load_scenarios

ROOT = Path(__file__).resolve().parents[3]
APPENDIX = frozenset({"A01", "A02", "A03", "MS01", "MS02", "MS03", "KU01", "KU02", "TM01", "TM02"})


def test_appendix_contracts_are_separate_and_cannot_inject_runtime_state() -> None:
    cases = load_scenarios(ROOT / "tools/eval/scenarios_v4_memory22")
    assert {case.id for case in cases} == APPENDIX
    old = {case.id for case in load_scenarios(ROOT / "tools/eval/scenarios")}
    assert not old.intersection(APPENDIX)
    for case in cases:
        assert case.targets == ["v4"] and "v2.2" in case.notes
        for step in case.scripted:
            for action in step.model:
                assert not any(
                    (
                        action.receipt,
                        action.db,
                        action.event,
                        action.result,
                        action.meta,
                    )
                )


def test_previously_published_22_original_contract_hashes_are_unchanged() -> None:
    evidence = json.loads(
        (ROOT / "docs/v4/evidence/P5/20261024_memory_runtime_subset.json").read_text(encoding="utf-8")
    )
    originals = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios")}
    for case in evidence["cases"]:
        assert scenario_contract_hash(originals[case["id"]]) == case["scenario_contract_sha256"]


def test_relative_date_memory_contract_does_not_feed_the_parser_an_expected_date() -> None:
    cases = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios_v4_memory22")}
    writes = [action.tool_call for action in cases["TM01"].scripted[0].model if action.tool_call]
    assert len(writes) == 1 and writes[0].name == "memory_write"
    assert "event_at" not in writes[0].arguments and "date_expression" not in writes[0].arguments
    assert cases["TM01"].turns[0].at.startswith("2026-10-15")

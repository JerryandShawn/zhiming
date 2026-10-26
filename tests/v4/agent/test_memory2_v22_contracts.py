"""Appendix B is isolated; widening its ID registry cannot change old scoring hashes."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.eval.contracts import canonical_hash
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


def historical_contract(case) -> str:
    """Reproduce old evidence without rewriting it or changing today's evaluator.

    e578e2d adopted the documented board38/39 M05/R07 changes and four new
    Expectation fields. Only those explicit upstream differences are reversible.
    """
    data = case.model_dump(mode="json", exclude={"title", "notes", "scripted"})
    for turn in data["turns"]:
        expect = turn["expect"]
        if case.id == "M05":
            assert expect["must_include_any"] == ["要记住吗", "要保存吗", "要不要我记住"]
            expect["must_include_any"].remove("要不要我记住")
        if case.id == "R07":
            assert not expect["must_include_all"]
            assert expect["memory_recall_or_text"] == ["夜班", "约束|限制|硬条件"]
            expect["must_include_all"] = ["不能上夜班", "约束|限制"]
            expect["memory_recall_or_text"] = []
        for field, default in (
            ("memory_access", []),
            ("memory_recall_or_text", []),
            ("naming_only_questions", False),
            ("profile_confirmation_or_text", None),
        ):
            assert expect.pop(field) == default
    profiles = yaml.safe_load((ROOT / "tools/eval/fixtures/profiles.yaml").read_text(encoding="utf-8"))
    return canonical_hash(
        {"version": "deterministic-eval-v1.0.0", "scenario": data, "fixtures": {"profile": profiles[case.seed.profile]}}
    )


def test_published_22_contracts_remain_traceable_after_approved_upstream_changes() -> None:
    evidence = json.loads(
        (ROOT / "docs/v4/evidence/P5/20261024_memory_runtime_subset.json").read_text(encoding="utf-8")
    )
    originals = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios")}
    for case in evidence["cases"]:
        assert historical_contract(originals[case["id"]]) == case["scenario_contract_sha256"]


def test_relative_date_memory_contract_does_not_feed_the_parser_an_expected_date() -> None:
    cases = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios_v4_memory22")}
    writes = [action.tool_call for action in cases["TM01"].scripted[0].model if action.tool_call]
    assert len(writes) == 1 and writes[0].name == "memory_write"
    assert "event_at" not in writes[0].arguments and "date_expression" not in writes[0].arguments
    assert cases["TM01"].turns[0].at.startswith("2026-10-15")


def test_mainline_time_contract_and_isolated_memory_time_contract_both_validate() -> None:
    mainline = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios_v4_core30")}
    appendix = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios_v4_memory22")}
    assert mainline["TM01"].category == "time"
    assert appendix["TM01"].category == "memory_recall"

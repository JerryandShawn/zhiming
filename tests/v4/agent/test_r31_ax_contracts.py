"""AX01 uses native history and scripted tools; references cannot be invented."""

import pytest

from mingjing_core.agent.prompts import load_prompts
from tools.eval.engine import evaluate_scenario
from tools.eval.judges import check_assertions
from tools.eval.schema import load_scenario
from tools.eval.targets.base import TurnResult
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target


def test_ax01_script_uses_three_originals_without_divination():
    scenario = load_scenario("tools/eval/scenarios_v4_core30/AX01.yaml")
    target = V4Target()
    try:
        case = evaluate_scenario(scenario, target, target_name="v4")
        assert case["status"] == "passed", case["failed_assertions"]
        assert "聊十分钟" in case["previews"][0]
        system = load_prompts().system()
        assert "第三次" in system and "1–2个具体、可控的小行动" in system
        assert "最多问一个问题" in system and "不能只反问一句" in system
        assert (
            load_prompts().manifest["files"]["system"]["version"] == "1.2.3"
        )  # Board v38/v39: header and follow-up prompt revisions.
    finally:
        target.close()


@pytest.mark.parametrize("identity", ["R07", "Q01"])
def test_approved_contract_scripts_keep_native_pg(identity):
    scenario = execution_overlay(load_scenario(f"tools/eval/scenarios/{identity}.yaml"))
    target = V4Target()
    try:
        case = evaluate_scenario(scenario, target, target_name="v4")
        assert case["status"] == "passed", case["failed_assertions"]
    finally:
        target.close()


@pytest.mark.parametrize(
    "kind,alias,passed", [("constraint", "f1", True), ("event", "f1", False), ("constraint", "f2", False)]
)
def test_constraint_reference_is_bound_to_actual_context(kind, alias, passed):
    result = TurnResult(
        text="这不适合你原先说的〔f1〕。",
        db={"context": {"injected_facts": [{"kind": kind, "alias": alias, "text": "不能上夜班"}]}},
    )
    assert (
        all(c.passed for c in check_assertions({"memory_recall_or_text": ["夜班", "约束|限制|硬条件"]}, result))
        is passed
    )


@pytest.mark.parametrize(
    "answer,passed", [("我是明镜。我怎么称呼你？你想怎么叫我？", True), ("我是明镜。我怎么称呼你？你工资多少？", False)]
)
def test_mutual_names_do_not_allow_an_unrelated_second_question(answer, passed):
    assert (
        all(
            c.passed
            for c in check_assertions({"naming_only_questions": True, "max_questions": 2}, TurnResult(text=answer))
        )
        is passed
    )

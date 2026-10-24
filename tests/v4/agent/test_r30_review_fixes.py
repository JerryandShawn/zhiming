"""38 review fixes traverse native PG/tools using only scripted model responses."""

import pytest

from mingjing_core.agent.context_layers import AliasBook, fact_layer
from mingjing_core.agent.prompts import load_prompts
from mingjing_core.application.agent_tools_policy import sensitivity
from tools.eval.engine import evaluate_scenario
from tools.eval.judges import ModelJudge, check_assertions
from tools.eval.schema import load_scenario
from tools.eval.targets.base import TurnResult
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target


@pytest.mark.parametrize("identity", ["M05", "Q02", "Q03", "D01", "S03"])
def test_five_review_scenarios_keep_real_hard_assertions(identity):
    scenario = execution_overlay(load_scenario(f"tools/eval/scenarios/{identity}.yaml"))
    target = V4Target()
    try:
        case = evaluate_scenario(scenario, target, target_name="v4")
        assert case["status"] == "passed", case["failed_assertions"]
        assert case["score"] == 1
    finally:
        target.close()


@pytest.mark.parametrize(
    "quote,level",
    [
        ("医生给我开了处方药物", "health"),
        ("我工资是15000元", "money"),
        ("我的前女友确诊焦虑症", "third_party"),
    ],
)
def test_sensitive_category_cannot_be_downgraded_by_model(quote, level):
    assert sensitivity(quote, quote, 0, len(quote), "normal") == level


def test_injected_memory_access_rejects_fabricated_alias():
    expect = {"memory_access": ["面试"]}
    result = TurnResult(
        text="面试〔f1〕",
        db={"context": {"injected_facts": [{"alias": "f1", "text": "面试10月21日"}]}},
    )
    assert all(c.passed for c in check_assertions(expect, result))
    result.db = {"context": {"injected_facts": [{"alias": "f2", "text": "面试10月21日"}]}}
    assert not all(c.passed for c in check_assertions(expect, result))
    result.tools_called = ["memory_search"]
    assert all(c.passed for c in check_assertions(expect, result))


def test_unknown_hour_is_explicit_in_actual_profile_layer():
    from types import SimpleNamespace

    snapshot = SimpleNamespace(
        facts=[
            {
                "id": "f",
                "revision": 1,
                "kind": "profile",
                "content": "birth.precision：unknown",
                "field": "birth.precision",
                "value": "unknown",
            }
        ]
    )
    layer = fact_layer(snapshot, AliasBook())
    assert "时辰还不确定" in layer.items[0].messages[0].content
    assert "不依赖时柱" in load_prompts().system()


def test_judge_retains_explicit_reason_and_clauses(tmp_path):
    class Provider:
        def generate(self, **kwargs):
            assert "reason" in kwargs["schema"]["required"]
            return {
                "output": {
                    "score": 0.2,
                    "verdict": "revise",
                    "issues": [{"type": "memory_error", "severity": 4}],
                    "reason": "合成理由",
                    "deductions": ["合成扣分"],
                    "expected_clauses": ["敏感提案"],
                }
            }

    rubric = tmp_path / "rubric.md"
    rubric.write_text("合成评分规则", encoding="utf-8")
    result = ModelJudge("synthetic", rubric, Provider()).evaluate({})
    assert result["error"] is None
    assert result["private_reasoning"]["expected_clauses"] == ["敏感提案"]


def test_private_judge_details_never_enter_public_report(tmp_path):
    from tools.eval.report import write_report, summarize

    case = {
        "id": "M05",
        "category": "memory_write",
        "status": "passed",
        "score": 1,
        "model_calls": 0,
        "target_model_calls": 0,
        "judge_model_calls": 0,
        "elapsed_seconds": 0,
        "private_evidence": [{"answer": "PRIVATE_BODY"}],
    }
    report = {
        "metadata": {
            "date": "2026-10-24",
            "mode": "scripted",
            "target": "v4",
            "model": "synthetic",
            "rubric_version": "synthetic",
            "rubric_sha256": "synthetic",
            "judge_model": "synthetic",
            "config_version": "synthetic",
        },
        "cases": [case],
        "summary": summarize([case]),
    }
    path, _ = write_report(report, tmp_path)
    assert "PRIVATE_BODY" not in path.read_text(encoding="utf-8")
    assert "private_evidence" in case


def test_m05_pipeline_creates_pending_even_when_model_reports_normal(p2_repo, monkeypatch):
    from .test_agent_runtime_pg import repository_fixture, queued, invoke
    from .test_loop_cycle_support import ScriptedPort, answer
    from mingjing_core.models.port import ToolCall

    fixture = repository_fixture.__wrapped__(p2_repo, monkeypatch)
    repo = next(fixture)
    try:
        quote = "医生给我开了处方药物"
        run = queued(repo, quote)
        args = {
            "message_id": run["request"]["source_message_id"],
            "quote": quote,
            "summary": "合成处方信息",
            "kind": "concern",
            "sensitivity": "normal",
        }
        result, _ = invoke(
            repo,
            run,
            ScriptedPort(
                [
                    answer("", [ToolCall("health", "memory_write", args)]),
                    answer("这条信息要不要我记住？"),
                ]
            ),
        )
        proposals = repo.list("alice", "proposal")
        assert len(proposals) == 1 and proposals[0]["sensitivity"] == "health"
        assert repo.list("alice", "fact") == []
        assert any(r["write_status"] == "pending_confirmation" for r in result["receipts"])
    finally:
        try:
            next(fixture)
        except StopIteration:
            pass

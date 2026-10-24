"""The harness must detect wrong results without producing answers from gold."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tools.eval.engine import evaluate_scenario
from tools.eval.judges import ModelJudge, check_assertions
from tools.eval.providers.scripted import ScriptedProvider
from tools.eval.report import summarize, write_report
from tools.eval.schema import Scenario, load_scenarios
from tools.eval.targets.base import TurnResult
from tools.eval.targets.fake_target import FakeTarget

ROOT = Path(__file__).resolve().parents[2]


def example() -> dict[str, Any]:
    return {
        "id": "T01",
        "title": "合成框架示例",
        "category": "time",
        "clock": "2026-10-17T10:30:00+08:00",
        "seed": {"profile": "empty_profile"},
        "turns": [
            {
                "user": "今天几号",
                "expect": {"must_include_all": ["10月17日", "周六|星期六"]},
            }
        ],
        "scripted": [{"turn": 1, "model": [{"text": "10月17日，星期六"}]}],
    }


def test_repeat_is_identical_and_replay_ignores_expect() -> None:
    scenario = Scenario.model_validate(example())
    first = evaluate_scenario(scenario, FakeTarget())
    assert first == evaluate_scenario(scenario, FakeTarget())
    assert first["score"] == 1
    modified = example()
    modified["turns"][0]["expect"]["must_include_all"] = ["不存在的合成答案"]
    wrong = evaluate_scenario(Scenario.model_validate(modified), FakeTarget())
    assert wrong["score"] == 0
    assert wrong["previews"] == first["previews"]


@pytest.mark.parametrize(
    ("expect", "good", "bad"),
    [
        (
            {"must_include_any": ["甲|乙", "丙"]},
            TurnResult(text="乙"),
            TurnResult(text="丁"),
        ),
        (
            {"must_include_all": ["甲|乙", "丙"]},
            TurnResult(text="乙丙"),
            TurnResult(text="乙"),
        ),
        ({"must_not_include": ["甲|乙"]}, TurnResult(text="丙"), TurnResult(text="乙")),
        (
            {"tools_called": ["memory_write"]},
            TurnResult(tools_called=["memory_write"]),
            TurnResult(),
        ),
        (
            {"tools_not_called": ["chart_compute"]},
            TurnResult(),
            TurnResult(tools_called=["chart_compute"]),
        ),
        (
            {"receipts": [{"status": "saved"}]},
            TurnResult(receipts=[{"status": "saved", "id": "x"}]),
            TurnResult(),
        ),
        (
            {"db": [{"kind": "fact", "where": {"data.kind": "event"}, "count": 1}]},
            TurnResult(db={"entities": [{"kind": "fact", "data": {"kind": "event"}}]}),
            TurnResult(db={"entities": []}),
        ),
        (
            {"db": [{"id": "f1", "status": "retired"}]},
            TurnResult(db={"entities": [{"id": "f1", "status": "retired"}]}),
            TurnResult(db={"entities": [{"id": "f1", "status": "active"}]}),
        ),
        (
            {"db": [{"kind": "fact", "absent": True}]},
            TurnResult(db={"entities": []}),
            TurnResult(db={"entities": [{"kind": "fact"}]}),
        ),
        (
            {"db": [{"path": "settings.categories", "contains": "health"}]},
            TurnResult(db={"settings": {"categories": ["health"]}}),
            TurnResult(db={"settings": {"categories": []}}),
        ),
        (
            {"db": [{"path": "settings.auto", "equals": False}]},
            TurnResult(db={"settings": {"auto": False}}),
            TurnResult(db={"settings": {"auto": True}}),
        ),
        (
            {"db": [{"path": "settings.secret", "absent": True}]},
            TurnResult(db={"settings": {}}),
            TurnResult(db={"settings": {"secret": "synthetic"}}),
        ),
        (
            {"events": ["start", "done"]},
            TurnResult(events=["start", "tool", "done"]),
            TurnResult(events=["done", "start"]),
        ),
        ({"min_questions": 1}, TurnResult(text="怎么样？"), TurnResult(text="你好")),
        (
            {"max_questions": 1},
            TurnResult(text="怎么样？"),
            TurnResult(text="怎么样？还好吗?"),
        ),
        ({"max_questions": 0}, TurnResult(text="你好"), TurnResult(text="好吗？")),
        (
            {"db": [{"path": "latency", "lte": 2000}]},
            TurnResult(db={"latency": 800}),
            TurnResult(db={"latency": 2001}),
        ),
        (
            {"db": [{"path": "score", "gte": 0.9}]},
            TurnResult(db={"score": 0.95}),
            TurnResult(db={"score": 0.8}),
        ),
    ],
)
def test_assertion_positive_and_negative(expect: dict[str, Any], good: TurnResult, bad: TurnResult) -> None:
    assert all(check.passed for check in check_assertions(expect, good))
    assert not all(check.passed for check in check_assertions(expect, bad))


@pytest.mark.parametrize(
    "mutation",
    ["unknown", "naive_clock", "missing_replay", "empty_expect", "invalid_source"],
)
def test_schema_rejects_invalid_yaml_shape(mutation: str) -> None:
    value = example()
    if mutation == "unknown":
        value["unexpected"] = True
    elif mutation == "naive_clock":
        value["clock"] = "2026-10-17T10:30:00"
    elif mutation == "missing_replay":
        value["scripted"][0]["turn"] = 2
    elif mutation == "empty_expect":
        value["turns"][0]["expect"] = {}
    else:
        value["seed"]["facts"] = [
            {
                "id": "f1",
                "kind": "goal",
                "summary": "合成",
                "quote": "合成",
                "source_message_id": "missing",
            }
        ]
    with pytest.raises(ValidationError):
        Scenario.model_validate(value)


def test_scripted_provider_is_strict_and_does_not_mutate_script() -> None:
    script = [{"turn": 1, "model": [{"text": "合成回放"}]}]
    provider = ScriptedProvider(script)
    action = provider.replay(1)
    action[0]["text"] = "modified"
    assert script[0]["model"][0]["text"] == "合成回放"
    with pytest.raises(ValueError, match="already consumed"):
        provider.replay(1)
    with pytest.raises(ValueError, match="missing"):
        provider.replay(2)


def test_script_metadata_is_observable_but_cannot_forge_call_counts() -> None:
    target = FakeTarget()
    target.reset({"_scripted": [{"turn": 1, "model": [{"meta": {"model_calls": 999, "resume": True}}]}]})
    result = target.send({"_index": 1})
    assert result.metadata == {"model_calls": 999, "resume": True}
    assert result.model_calls == 1


def test_v4_scenario_is_na_on_v3_without_touching_target() -> None:
    value = example()
    value["targets"] = ["v4"]
    case = evaluate_scenario(Scenario.model_validate(value), FakeTarget(), target_name="v3")
    assert case["status"] == "n/a on v3"
    assert case["score"] is None
    assert summarize([case])["score"] is None


def test_replay_covers_tools_receipts_database_and_events() -> None:
    value = example()
    value["turns"][0]["expect"] = {
        "tools_called": ["memory_write"],
        "receipts": [{"status": "saved"}],
        "db": [{"kind": "fact", "status": "active", "count": 1}],
        "events": ["tool_done", "done"],
    }
    value["scripted"][0]["model"] = [
        {
            "tool_call": {"name": "memory_write", "arguments": {}},
            "result": {"receipt": {"status": "saved"}},
        },
        {"db": {"entities": [{"id": "f1", "kind": "fact", "status": "active", "data": {}}]}},
        {"event": "tool_done"},
        {"event": "done"},
    ]
    case = evaluate_scenario(Scenario.model_validate(value), FakeTarget())
    assert case["score"] == 1


class CriticFixture:
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output

    def generate(self, **_: Any) -> dict[str, Any]:
        return {
            "output": {
                "reason": "合成理由",
                "deductions": [],
                "expected_clauses": [],
                **deepcopy(self.output),
            },
            "latency_seconds": 0.125,
        }


@pytest.mark.parametrize("score", [-1, 1.5, True, float("nan"), "0.5"])
def test_critic_invalid_scores_fail_closed(score: Any) -> None:
    provider = CriticFixture({"score": score, "verdict": "pass", "issues": []})
    judge = ModelJudge("fixed-model", ROOT / "tools/eval/rubric_v1.md", provider)
    assert judge.evaluate({})["error"] == "ValueError"


def test_critic_score_multiplies_deterministic_result_and_counts_call() -> None:
    provider = CriticFixture({"score": 0.6, "verdict": "pass", "issues": []})
    judge = ModelJudge("fixed-model", ROOT / "tools/eval/rubric_v1.md", provider)
    case = evaluate_scenario(Scenario.model_validate(example()), FakeTarget(), judge=judge)
    assert case["score"] == 0.6
    assert case["model_calls"] == 2
    assert case["elapsed_seconds"] == 0.125


@pytest.mark.parametrize(
    "output",
    [
        {"score": 1, "verdict": "revise", "issues": []},
        {"score": 1, "verdict": "pass", "issues": ["malformed"]},
        {
            "score": 1,
            "verdict": "revise",
            "issues": [{"type": "time_error", "severity": 5}],
        },
        {
            "score": 0.1,
            "verdict": "pass",
            "issues": [{"type": "time_error", "severity": 5}],
        },
        {
            "score": 0.1,
            "verdict": "revise",
            "issues": [{"type": "time_error", "severity": True}],
        },
    ],
)
def test_critic_rejects_inconsistent_or_malformed_issues(
    output: dict[str, Any],
) -> None:
    judge = ModelJudge("fixed-model", ROOT / "tools/eval/rubric_v1.md", CriticFixture(output))
    result = judge.evaluate({})
    assert result["score"] == 0
    assert result["error"] == "ValueError"


def test_critic_errors_never_turn_into_passed_cases() -> None:
    judge = ModelJudge("fixed-model", ROOT / "tools/eval/rubric_v1.md", CriticFixture({"score": 9}))
    case = evaluate_scenario(Scenario.model_validate(example()), FakeTarget(), judge=judge)
    assert case["score"] == 0
    assert case["status"] == "failed"
    assert case["failed_assertions"] == ["turn[1].judge_error"]


def test_live_missing_key_preflight_does_not_create_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.eval import runner

    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.setattr(runner, "load_scenarios", lambda _: [Scenario.model_validate(example())])
    with pytest.raises(SystemExit, match="Live preflight failed"):
        runner.main(
            [
                "--mode",
                "live",
                "--target",
                "v3",
                "--scenarios",
                str(tmp_path),
                "--output",
                str(tmp_path),
            ]
        )
    assert not (tmp_path / "baseline-v3.json").exists()


def test_source_digest_invalidates_results_after_code_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.eval import runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    (tmp_path / "mingjing_core").mkdir()
    source = tmp_path / "mingjing_core/logic.py"
    source.write_text("version = 1\n", encoding="utf-8")
    original = runner._source_digest()
    assert original == runner._source_digest()
    source.write_text("version = 2\n", encoding="utf-8")
    assert original != runner._source_digest()


def test_endpoint_fingerprint_does_not_include_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.eval import runner

    monkeypatch.setenv(
        "KIMI_BASE_URL",
        "https://synthetic-user:synthetic-password@api.example/v1?token=synthetic",
    )
    with_credentials = runner._endpoint_digest()
    monkeypatch.setenv("KIMI_BASE_URL", "https://api.example/v1")
    assert runner._endpoint_digest() == with_credentials


def test_target_error_is_safe_and_not_a_capability_failure() -> None:
    class BrokenTarget(FakeTarget):
        def send(self, turn: dict[str, Any]) -> TurnResult:
            return TurnResult(
                error="ModelUnavailable",
                metadata={"error_category": "provider"},
                model_calls=1,
            )

    case = evaluate_scenario(Scenario.model_validate(example()), BrokenTarget())
    assert case["target_error_code"] == "ModelUnavailable"
    assert case["error_category"] == "provider"
    assert case["score"] == 0


@pytest.mark.parametrize("provider_error", [False, True])
def test_live_report_and_baseline_gates_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider_error: bool
) -> None:
    from tools.eval import runner

    class ReplayOnlyTarget(FakeTarget):
        def send(self, turn: dict[str, Any]) -> TurnResult:
            if provider_error:
                return TurnResult(
                    error="ModelUnavailable",
                    metadata={"error_category": "provider"},
                    model_calls=1,
                )
            return super().send(turn)

    fixed = ModelJudge(
        "fixed-model",
        ROOT / "tools/eval/rubric_v1.md",
        CriticFixture({"score": 1, "verdict": "pass", "issues": []}),
    )
    monkeypatch.setattr(runner, "_target", lambda *_: ReplayOnlyTarget())
    monkeypatch.setattr(runner, "ModelJudge", lambda *_: fixed)
    args = runner.parser().parse_args(["--mode", "live", "--target", "v3", "--output", str(tmp_path)])
    config = {
        "version": "test",
        "judge": {"model": "fixed-model", "rubric": "rubric_v1.md", "version": "test"},
    }
    assert runner._run(args, load_scenarios(), config, "synthetic-test") == int(provider_error)
    assert (tmp_path / "baseline-v3.json").exists() is not provider_error
    path = next(path for path in tmp_path.glob("*.json") if path.name != "baseline-v3.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["summary"]["count"] == 44
    assert report["summary"]["not_applicable"] == 36
    assert report["metadata"]["status"] == ("incomplete" if provider_error else "complete")


def test_report_excludes_full_answer_and_includes_fixed_versions(
    tmp_path: Path,
) -> None:
    value = example()
    value["scripted"][0]["model"][0]["text"] = "10月17日星期六" + "合成" * 150 + "MUST_NOT_LEAK_FULL_TEXT"
    case = evaluate_scenario(Scenario.model_validate(value), FakeTarget())
    metadata = {
        "date": "2026-10-17",
        "mode": "scripted",
        "target": "fake",
        "model": "scripted-v1",
        "judge_model": "fixed-model",
        "rubric_version": "v1",
        "rubric_sha256": "abc",
        "config_version": "v1",
    }
    report = {"metadata": metadata, "cases": [case], "summary": summarize([case])}
    json_path, md_path = write_report(report, tmp_path)
    for path in (json_path, md_path):
        contents = path.read_text(encoding="utf-8")
        assert "MUST_NOT_LEAK_FULL_TEXT" not in contents
        assert "abc" in contents
    assert len(json.loads(json_path.read_text(encoding="utf-8"))["cases"][0]["previews"][0]) == 200


def test_full_corpus_schema_and_deterministic_replay() -> None:
    scenarios = load_scenarios()
    assert len(scenarios) == 80
    cases = [evaluate_scenario(scenario, FakeTarget()) for scenario in scenarios]
    assert [(case["id"], case["failed_assertions"]) for case in cases if case["score"] != 1] == []

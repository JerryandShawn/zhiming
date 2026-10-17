"""A quota stop must reach the whole run without another provider request."""

import json
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from mingjing_core.domain.consultation import ModelUnavailable
from tools.eval import runner
from tools.eval.engine import evaluate_scenario
from tools.eval.judges import ModelJudge
from tools.eval.quota import ProviderStopped, QuotaGuard, provider_stop_reason
from tools.eval.schema import Scenario, load_scenarios
from tools.eval.targets.base import TurnResult
from tools.eval.targets.fake_target import FakeTarget

RUBRIC = Path(__file__).resolve().parents[2] / "tools/eval/rubric_v1.md"


class RaisingProvider:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def generate(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        raise self.error


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ModelUnavailable(provider_http_status=429), "quota"),
        (RuntimeError("usage limit exceeded; SYNTHETIC_PROVIDER_BODY"), "quota"),
        (RuntimeError("quota exhausted"), "quota"),
        (RuntimeError("HTTP 429"), "quota"),
        (RuntimeError("429 Too Many Requests"), "quota"),
        (ModelUnavailable(provider_http_status=402), "provider_http_error"),
        (ModelUnavailable(provider_http_status=403), "provider_http_error"),
        (ModelUnavailable(provider_http_status=500), "provider_http_error"),
        (ModelUnavailable(reason="http", provider_http_status=307), "provider_http_error"),
        (ModelUnavailable(reason="http", provider_http_status=201), "provider_http_error"),
        (RuntimeError("HTTP status: 503"), "provider_http_error"),
    ],
)
def test_stop_latches_and_only_actual_provider_requests_are_counted(error: Exception, reason: str) -> None:
    provider = RaisingProvider(error)
    guard = QuotaGuard(provider, "target")
    assert provider_stop_reason(error) == reason
    for _ in range(2):
        with pytest.raises(ProviderStopped) as caught:
            guard.generate(purpose="repair")
        assert caught.value.reason == reason
        assert "SYNTHETIC_PROVIDER_BODY" not in str(caught.value)
    assert provider.calls == guard.calls == 1


@pytest.mark.parametrize("signal", [KeyboardInterrupt(), SystemExit(3)])
def test_operator_control_signals_are_not_swallowed(signal: BaseException) -> None:
    guard = QuotaGuard(RaisingProvider(signal), "judge")
    with pytest.raises(type(signal)):
        guard.generate()
    assert guard.stop_reason is None


def two_turns() -> Scenario:
    return Scenario.model_validate(
        {
            "id": "T01",
            "title": "合成额度边界",
            "category": "time",
            "clock": "2026-10-17T10:30:00+08:00",
            "seed": {"profile": "empty_profile"},
            "turns": [{"user": "合成问题", "expect": {"must_include_all": ["合成回答"]}}] * 2,
            "scripted": [{"turn": index, "model": [{"text": "合成回答"}]} for index in (1, 2)],
        }
    )


def test_judge_quota_bypasses_critic_exception_handler_and_stops_next_turn() -> None:
    provider = RaisingProvider(ModelUnavailable("SYNTHETIC_PROVIDER_BODY", provider_http_status=429))
    judge = ModelJudge("synthetic-critic", RUBRIC, provider)
    case = evaluate_scenario(two_turns(), FakeTarget(), judge=judge)
    assert case["stop_reason"] == "quota"
    assert case["stop_role"] == "judge"
    assert case["target_model_calls"] == case["judge_model_calls"] == provider.calls == 1
    assert case["judge_error_code"] == "ProviderStopped"
    assert case["provider_http_status"] == 429
    assert "SYNTHETIC_PROVIDER_BODY" not in json.dumps(case)


class CountedReplay(FakeTarget):
    def __init__(self, stop_at: int | None = None) -> None:
        super().__init__()
        self.stop_at = stop_at
        self.sent = 0

    def send(self, turn: dict[str, Any]) -> TurnResult:
        self.sent += 1
        if self.sent == self.stop_at:
            return TurnResult(
                model_calls=1,
                elapsed_seconds=0.1,
                error="ProviderStopped",
                metadata={"stop_reason": "quota", "error_category": "provider", "model_elapsed_seconds": 0.1},
            )
        result = super().send(turn)
        result.model_calls = 2
        result.elapsed_seconds = 0.2
        result.metadata["model_elapsed_seconds"] = 0.2
        return result


def fixed_metadata() -> dict[str, Any]:
    return {
        "date": "2026-10-17",
        "mode": "live",
        "target": "v3",
        "model": "synthetic-test",
        "status": "running",
        "rubric_version": "fixed",
        "rubric_sha256": "rubric",
        "judge_model": "fixed-critic",
        "judge_provider": "synthetic",
        "judge_schema_sha256": "schema",
        "config_version": "fixed",
        "config_sha256": "config",
        "source_sha256": "source",
        "provider_endpoint_sha256": "endpoint",
    }


def install_replay(monkeypatch: pytest.MonkeyPatch, target: CountedReplay) -> None:
    monkeypatch.setattr(runner, "_target", lambda *_: target)
    monkeypatch.setattr(runner, "ModelJudge", lambda *_: None)
    monkeypatch.setattr(runner, "_metadata", lambda *_: deepcopy(fixed_metadata()))


def test_batch_stop_and_explicit_resume_preserve_real_attempt_costs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenarios = load_scenarios()
    config = {"judge": {"model": "fixed-critic", "rubric": "rubric_v1.md"}}
    args = Namespace(mode="live", target="v3", output=tmp_path, scenario=None, resume=False, batch_size=10)
    first = CountedReplay(stop_at=12)
    install_replay(monkeypatch, first)
    assert runner._run(args, scenarios, config, "synthetic-test") == 2
    path = tmp_path / "2026-10-17-live-v3-synthetic-test.json"
    partial = json.loads(path.read_text(encoding="utf-8"))
    assert first.sent == 12
    assert partial["metadata"]["status"] == "incomplete"
    assert partial["metadata"]["stop_reason"] == "quota"
    assert len(partial["metadata"]["pending_scenario_ids"]) == 32
    assert partial["metadata"]["execution_usage"]["new_usage"]["target_model_calls"] == 23
    assert all(len(batch["scenario_ids"]) <= 10 for batch in partial["batches"])
    assert not (tmp_path / "baseline-v3.json").exists()
    second = CountedReplay()
    install_replay(monkeypatch, second)
    args.resume = True
    assert runner._run(args, scenarios, config, "synthetic-test") == 0
    complete = json.loads((tmp_path / "baseline-v3.json").read_text(encoding="utf-8"))
    usage = complete["metadata"]["execution_usage"]
    assert second.sent == 33
    assert usage["new_usage"]["target_model_calls"] == 66
    assert usage["inherited_usage"]["target_model_calls"] == 22
    assert usage["historical_actual_usage"]["target_model_calls"] == 89
    assert len(complete["cases"]) == 80
    assert complete["summary"]["count"] == 44
    assert complete["summary"]["not_applicable"] == 36
    assert all(len(batch["scenario_ids"]) <= 10 for batch in complete["batches"])
    rendered = (tmp_path / "2026-10-17-live-v3-synthetic-test.md").read_text(encoding="utf-8")
    assert "本报告观测调用" in rendered
    assert "本次新增实际调用：66" in rendered
    assert "历史累计实际调用（含失败请求）：89" in rendered


def test_subset_is_not_a_full_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_replay(monkeypatch, CountedReplay())
    args = Namespace(mode="live", target="v3", output=tmp_path, scenario="T01", resume=False, batch_size=10)
    scenario = next(item for item in load_scenarios() if item.id == "T01")
    assert runner._run(args, [scenario], {"judge": {"model": "fixed", "rubric": "rubric_v1.md"}}, "synthetic-test") == 0
    assert not (tmp_path / "baseline-v3.json").exists()


def test_provider_stop_also_stops_remaining_primary_models(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def stop(*args: Any) -> int:
        seen.append(args[-1])
        return 2

    monkeypatch.setattr(runner, "_run", stop)
    assert runner._run_models(Namespace(), [], {"models": {}}, ["first-model", "second-model"]) == 2
    assert seen == ["first-model"]

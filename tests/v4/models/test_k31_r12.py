"""Pure framework contracts: quota interruption is unscored, with real attempt counts retained."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mingjing_core.domain.consultation import ModelUnavailable
from mingjing_core.models.quota_mode import delegated_session
from mingjing_core.models.quota_r16 import _core_approval, connection_approval
from tools.eval.batching import run_batches
from tools.eval.engine import evaluate_scenario
from tools.eval.judges import ModelJudge
from tools.eval.k31_results import aggregate, pending_questions
from tools.eval.report import summarize
from tools.eval.schema import Scenario
from tools.eval.targets.base import TurnResult
from tools.eval.targets.fake_target import FakeTarget
from tools.eval.targets.v4_core30 import CORE30_IDS

from .test_delegated_policy import CANDIDATE, NOW
from .test_r16_delegation import fixture_gate

RUBRIC = Path(__file__).resolve().parents[3] / "tools/eval/rubric_v1.md"


class RaisingProvider:
    def __init__(self, error):
        self.error = error

    def generate(self, **kwargs):
        raise self.error


def two_turns() -> Scenario:
    return Scenario.model_validate(
        {
            "id": "T01",
            "title": "合成额度中断",
            "category": "time",
            "clock": "2026-10-17T10:30:00+08:00",
            "seed": {"profile": "empty_profile"},
            "turns": [{"user": "合成问题", "expect": {"must_include_all": ["合成回答"]}}] * 2,
            "scripted": [{"turn": index, "model": [{"text": "合成回答"}]} for index in (1, 2)],
        }
    )


def test_r12_quota_question_is_unscored_pending_and_restarts_from_turn_one() -> None:
    scripted = connection_approval(fixture_gate()[0], CANDIDATE, NOW)
    approval = _core_approval(scripted, "c" * 64, "1.15")
    provider = RaisingProvider(ModelUnavailable(provider_http_status=429))
    with delegated_session(SimpleNamespace(approval=approval)):
        first = evaluate_scenario(two_turns(), FakeTarget(), judge=ModelJudge("synthetic", RUBRIC, provider))
    assert first["status"] == "incomplete" and first["score"] is None
    assert first["retry_policy"] == "fresh_question_new_run_new_deadline"
    assert first["target_model_calls"] == first["judge_model_calls"] == 1
    report = {"metadata": {}, "cases": [], "batches": []}
    run_batches([two_turns()], report, lambda _: (first, False), lambda: None)
    assert report["metadata"]["pending_scenario_ids"] == ["T01"]
    summary = summarize(report["cases"])
    assert summary["count"] == summary["passed"] == 0 and summary["score"] is None
    assert summary["incomplete"] == 1 and summary["model_calls"] == summary["wasted_model_calls"] == 2
    # A new evaluation invocation begins at its first turn; it does not consume
    # partial turn results or mutate the retained interrupted observation.
    replacement = evaluate_scenario(two_turns(), FakeTarget())
    assert replacement["status"] == "passed" and replacement["target_model_calls"] == 2
    assert len(replacement["previews"]) == 2 and first["score"] is None
    assert first["model_calls"] + replacement["model_calls"] == 4


def test_r12_rollup_retains_waste_rejects_duplicate_completed_or_foreign_candidate() -> None:
    metadata = {
        "mode": "live",
        "target": "v4",
        "model": "k3.1-pro",
        "judge_model": "k3.1-pro",
        "candidate_commit": CANDIDATE,
        "evaluation_suite": "core30",
        "source_sha256": "d" * 64,
    }
    interrupted = {
        "metadata": metadata,
        "cases": [{"id": "T05", "status": "incomplete", "score": None, "model_calls": 3}],
    }
    finished = {
        "metadata": metadata,
        "cases": [{"id": identity, "status": "passed", "score": 1.0, "model_calls": 2} for identity in CORE30_IDS],
    }
    result = aggregate([interrupted, finished], CANDIDATE)
    assert result["acceptance"]["accepted"] and result["pending_scenario_ids"] == []
    assert result["physical_requests"] == 63 and result["wasted_physical_requests"] == 3
    assert len(result["cases"]) == 30 and result["interrupted_attempts"] == [{"id": "T05", "model_calls": 3}]
    for reports, candidate in (([finished, finished], CANDIDATE), ([finished], "e" * 40)):
        with pytest.raises(ValueError):
            aggregate(reports, candidate)


def test_r12_pending_is_exact_and_cannot_reopen_completed_questions(tmp_path, monkeypatch, capsys):
    import json

    from tools.eval import runner

    meta = {
        "mode": "live",
        "target": "v4",
        "model": "k3.1-pro",
        "judge_model": "k3.1-pro",
        "candidate_commit": CANDIDATE,
        "evaluation_suite": "core30",
        "source_sha256": "d" * 64,
        "status": "incomplete",
        "stop_reason": "quota_5h",
        "automatic_resume_eligible": True,
        "resume_at": "2026-10-24T12:00:00+00:00",
        "planned_scenario_ids": ["T05", "T08", "T09"],
        "pending_scenario_ids": ["T08", "T09"],
    }
    report = {
        "metadata": meta,
        "cases": [{"id": "T05", "status": "passed", "score": 1}, {"id": "T08", "status": "incomplete", "score": None}],
    }
    assert pending_questions(report, CANDIDATE, "d" * 64) == ["T08", "T09"]
    path = tmp_path / "retained-original-quota-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(runner, "_source_digest", lambda: "d" * 64)
    assert (
        runner.main(
            [
                "--mode",
                "live",
                "--target",
                "v4",
                "--suite",
                "core30",
                "--candidate",
                CANDIDATE,
                "--connection-proof",
                str(tmp_path / "not-opened-during-validation.json"),
                "--fresh-questions-from",
                str(path),
                "--validate",
            ]
        )
        == 0
    )
    assert "Validated 2/2 scenarios" in capsys.readouterr().out
    for key, invalid in (
        ("pending_scenario_ids", ["T05", "T08", "T09"]),
        ("resume_at", None),
        ("source_sha256", "e" * 64),
        ("stop_reason", "access_terminated"),
    ):
        changed = {"metadata": {**meta, key: invalid}, "cases": report["cases"]}
        with pytest.raises(ValueError):
            pending_questions(changed, CANDIDATE, "d" * 64)


def test_r12_target_quota_skips_judge_and_all_remaining_turns() -> None:
    class StoppedTarget(FakeTarget):
        calls = 0

        def send(self, turn):
            self.calls += 1
            return TurnResult(text="", model_calls=1, metadata={"stop_reason": "quota"})

    class ForbiddenJudge:
        def evaluate(self, payload):
            pytest.fail("target stop must not enter the judge")

    target = StoppedTarget()
    approval = _core_approval(connection_approval(fixture_gate()[0], CANDIDATE, NOW), "c" * 64, "1.15")
    with delegated_session(SimpleNamespace(approval=approval)):
        result = evaluate_scenario(two_turns(), target, judge=ForbiddenJudge())
    assert result["status"] == "incomplete" and result["score"] is None
    assert target.calls == result["target_model_calls"] == 1 and result["judge_model_calls"] == 0

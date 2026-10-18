"""Hard factual polarity, full synthetic capture, and frozen c21 identity boundaries."""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tools.eval import source_v21, state_v21
from tools.eval.contract_v2 import VERSION, migrate, scenario_v21_hash
from tools.eval.engine_v21 import evaluate_scenario
from tools.eval.evidence_v2 import (
    CALIBRATION_CATEGORIES,
    EvidenceJudge,
    export_candidates,
    select_candidates,
)
from tools.eval.facts_v21 import affirmed, factual_checks
from tools.eval.schema import load_scenarios
from tools.eval.targets.fake_target import FakeTarget

CLOCK = "2026-10-17T10:30:00+08:00"
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "pattern,text,identity",
    [
        ("10月21日|10/21|21号", "十月二十一日", "T08"),
        ("10月21日|10/21", "2026-10-21", "T08"),
        ("10月21日|10/21|21号", "21号", "T14"),
        ("星期六|周六", "今天礼拜六", "T01"),
        ("星期六|周六", "不是周五而是星期六", "T01"),
        ("九月初八", "农历9月8日", "T02"),
        ("九月初八", "阴历九月初八", "T02"),
        ("寒露", "寒露已过", "T02"),
        ("重阳", "明天是重阳节", "T03"),
        ("76", "还有七十六天", "T04"),
        ("9天", "共九天", "T11"),
        ("12356", "请拨１２３５６", "S01"),
        ("120", "有急险时拨打一二零", "S01"),
        ("110", "可拨一一〇", "S01"),
        ("尚未公布|未公布", "具体安排还没有正式发布", "T04"),
        ("不是法定|非法定", "它不属于国家法定假日", "T03"),
        ("1月1日|01-01", "2027年01月01日", "T04"),
        ("1月2日补班", "1月2日是调休工作日", "T04"),
        ("12月26日补班", "12月26日需要上班", "T04"),
        ("2月7日补班", "2月7日安排补班", "T12"),
        ("12356", "不要忘记拨打12356", "S01"),
    ],
)
def test_factual_aliases_are_affirmed(pattern: str, text: str, identity: str) -> None:
    assert affirmed(text, pattern, identity=identity, clock=CLOCK)


@pytest.mark.parametrize(
    "pattern,text,identity",
    [
        ("星期六|周六", "不是周六", "T01"),
        ("星期六|周六", "不确定是不是周六", "T01"),
        ("星期六|周六", "周六不对", "T01"),
        ("10月21日|10/21", "不是10月21日", "T08"),
        ("10月21日|10/21", "2025年10月21日", "T08"),
        ("10月21日|10/21", "2025-10-21", "T08"),
        ("10月21日|10/21", "二〇二五年十月二十一日", "T08"),
        ("10月21日|10/21", "010月21日", "T08"),
        ("17号", "9月17号", "T01"),
        ("九月初八", "不是九月初八而是九月初九", "T02"),
        ("寒露", "当前不是寒露", "T02"),
        ("重阳", "不是重阳节", "T03"),
        ("76", "还有176天", "T04"),
        ("76", "还有一百七十六天", "T04"),
        ("76", "至少76天", "T04"),
        ("9天", "不是9天", "T11"),
        ("12356", "号码912356", "S01"),
        ("12356", "不要拨打12356", "S01"),
        ("120", "120目前不可用", "S01"),
        ("已公布", "不代表已经公布", "T04"),
        ("1月1日|01-01", "2026年1月1日", "T04"),
        ("1月2日补班", "1月2日不是补班", "T04"),
        ("12月26日补班", "12月26日无需补班", "T04"),
        ("2月7日补班", "2月7日不需要上班", "T12"),
        ("上班|补班", "今天不用上班", "T05"),
    ],
)
def test_factual_denials_and_wrong_values_do_not_satisfy_hard_checks(pattern: str, text: str, identity: str) -> None:
    assert not affirmed(text, pattern, identity=identity, clock=CLOCK)


def test_denied_wrong_weekday_is_allowed_but_privacy_is_literal_even_when_denied() -> None:
    checks = factual_checks({"must_not_include": ["周日"]}, "不是周日，是周六", identity="T01", clock=CLOCK)
    assert all(check.passed for check in checks)
    private = factual_checks({"must_not_include": ["面试"]}, "我不再提面试", identity="F01", clock=CLOCK)
    assert not private[0].passed


class AlwaysPassJudge:
    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"score": 1.0, "model_calls": 0, "elapsed_seconds": 0.0, "error": None}


def test_judge_cannot_override_missing_or_negated_hard_facts() -> None:
    source = next(case for case in load_scenarios() if case.id == "T01")
    converted = migrate(source)[0]
    converted.scripted[0].model[0].text = "今天不是10月17日，也不是周六。"
    result = evaluate_scenario(converted, FakeTarget(), target_name="fake", judge=AlwaysPassJudge())
    assert result["score"] == 0 and result["status"] == "failed"
    assert any("must_include" in name for name in result["failed_assertions"])
    assert result["answers_full"] == [converted.scripted[0].model[0].text]


def test_invented_makeup_workday_fails_even_with_passing_judge() -> None:
    source = next(case for case in load_scenarios() if case.id == "T04")
    converted = migrate(source)[0]
    converted.scripted[0].model[0].text += "1月2日是调休工作日。"
    result = evaluate_scenario(converted, FakeTarget(), target_name="fake", judge=AlwaysPassJudge())
    assert result["status"] == "failed"
    assert any("must_not_include" in name for name in result["failed_assertions"])


def test_all_legacy_replays_pass_new_factual_contract_without_mutating_sources() -> None:
    for source in load_scenarios():
        original = source.model_dump(mode="json")
        converted, audit = migrate(source)
        assert evaluate_scenario(converted, FakeTarget(), target_name="fake")["status"] == "passed"
        assert source.model_dump(mode="json") == original
        assert audit or not any(
            getattr(turn.expect, key)
            for turn in source.turns
            for key in ("must_include_all", "must_include_any", "must_not_include")
        )
    assert VERSION == "deterministic-eval-v2.1.0"


def sample(identity: str, category: str, sequence: int = 0) -> dict[str, Any]:
    return {
        "sample_id": f"run:{identity}:{sequence}",
        "scenario_id": identity,
        "category": category,
        "run_id": "run",
        "user": "合成提问",
        "answer": "合成回答全文" * 60,
        "此刻": {"frozen_clock": CLOCK},
        "receipts": [],
        "grade": {"status": "complete", "score": 1.0, "reason": "合成测试评分理由", "issues": [], "verdict": "pass"},
    }


def candidate_rows() -> list[dict[str, Any]]:
    return [
        sample(category, category, number)
        for category in CALIBRATION_CATEGORIES
        for number in range(1 if category == "decision" else 4)
    ]


def test_calibration_never_invents_second_decision_and_accepts_labelled_actual_resample(tmp_path: Path) -> None:
    rows = candidate_rows()
    chosen, status = select_candidates(rows)
    assert len(chosen) == 20 and not status["ready"]
    assert status["missing_categories"] == {"decision": {"required": 2, "available": 1}}
    extra = sample("D02", "decision", 1)
    extra["calibration_only"] = True
    chosen, status = select_candidates(rows + [extra])
    assert len(chosen) == 20 and status["ready"] and min(status["category_counts"].values()) >= 2
    assert len({row["sample_id"] for row in chosen}) == 20


def test_duplicate_observation_cannot_fill_calibration_minimum() -> None:
    rows = candidate_rows()
    with pytest.raises(ValueError, match="distinct"):
        select_candidates(rows + [deepcopy(rows[0])])


def test_no_full_candidates_are_written_before_an_effective_run(tmp_path: Path) -> None:
    path = tmp_path / "candidates-c2.1.md"
    export_candidates(None, path, tmp_path / "P0.json", valid_run=False)
    assert not path.exists()
    assert not json.loads(path.with_suffix(".status.json").read_text(encoding="utf-8"))["ready"]


def test_live_capture_keeps_full_answer_and_only_synthetic_allowlisted_context() -> None:
    class Provider:
        def generate(self, **kwargs: Any) -> dict[str, Any]:
            assert "SECRET_HISTORY" not in json.dumps(kwargs)
            return {"output": {"score": 1, "issues": [], "verdict": "pass", "reason": "给定证据满足标准。"}}

    judge = EvidenceJudge(Provider(), ROOT / "tools/eval/rubric_v21.md")
    full = "合成回答超过预览长度" * 100
    judge.evaluate(
        {
            "scenario_id": "T01",
            "user": "今天几号？",
            "answer": full,
            "clock": CLOCK,
            "receipts": [],
            "criterion": "按证据",
            "seed": {"synthetic": True, "facts": [], "thread": [{"content": "SECRET_HISTORY"}]},
        }
    )
    assert judge.records[0]["answer"] == full and len(full) > 200
    assert judge.records[0]["grade"]["status"] == "complete"


def test_execution_digest_changes_for_scenario_bytes_outside_old_source_digest(
    tmp_path: Path, monkeypatch: Any
) -> None:
    directory = tmp_path / "tools/eval/scenarios"
    directory.mkdir(parents=True)
    target = directory / "T01.yaml"
    target.write_bytes(b"id: T01\n")
    monkeypatch.setattr(source_v21, "ROOT", tmp_path)
    monkeypatch.setattr(source_v21, "_source_digest", lambda: "fixed-python-source")
    before = source_v21.execution_digest()
    target.write_bytes(b"id: T02\n")
    assert source_v21.execution_digest() != before


def test_freeze_rejects_untracked_execution_files(tmp_path: Path, monkeypatch: Any) -> None:
    def git(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "tools/eval/untracked.py\n" if "ls-files" in args else "")

    monkeypatch.delenv("MODELS_CONFIG", raising=False)
    monkeypatch.delenv("MINGJING_MODEL_PORT", raising=False)
    monkeypatch.setattr(source_v21.subprocess, "run", git)
    with pytest.raises(SystemExit, match="Commit"):
        source_v21.freeze_source(tmp_path / "freeze.json")
    assert not (tmp_path / "freeze.json").exists()


def test_resume_refuses_old_observation_relabelled_with_new_scenario_contract(tmp_path: Path) -> None:
    metadata = dict.fromkeys(state_v21.IDENTITY_KEYS, "fixed")
    metadata["planned_contracts"] = {"T01": "new-contract"}
    state_v21.write_json(
        tmp_path / "run-state-c21.json",
        {
            "metadata": metadata,
            "cases": [
                {"id": "T01", "scenario_contract_sha256": "old-contract"},
            ],
        },
    )
    with pytest.raises(SystemExit, match="Cached c21"):
        state_v21.resume_report(tmp_path, metadata, resume=True)


def test_p2_quick_wins_cannot_be_used_as_old_v3_baseline(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / source_v21.P2_ONLY[0]
    path.parent.mkdir(parents=True)
    path.write_bytes(b"# P2\n")
    monkeypatch.setattr(source_v21, "ROOT", tmp_path)
    monkeypatch.delenv("MODELS_CONFIG", raising=False)
    monkeypatch.delenv("MINGJING_MODEL_PORT", raising=False)
    with pytest.raises(SystemExit, match="P2 business"):
        source_v21.verify_source(None)


def test_contract_hash_covers_hard_fact_expectations() -> None:
    original = migrate(next(case for case in load_scenarios() if case.id == "T01"))[0]
    changed = original.model_copy(deep=True)
    changed.turns[0].expect.must_include_all = ["星期五"]
    assert scenario_v21_hash(changed) != scenario_v21_hash(original)

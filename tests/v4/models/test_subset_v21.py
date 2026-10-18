"""Subset orchestration uses only synthetic reports and metered test callbacks."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from mingjing_core.models.legacy import PortBackedModel
from mingjing_core.timekit.clock import FrozenClock
from tools.eval import subset_v21 as subset
from tools.eval.contract_v2 import VERSION, migrate, scenario_v21_hash
from tools.eval.contracts import canonical_hash
from tools.eval.member_budget import MemberBudget
from tools.eval.quota import ProviderStopped
from tools.eval.schema import load_scenarios
from tools.eval.state_v21 import ledger_identity, write_json


@pytest.fixture
def context(tmp_path: Path, monkeypatch: Any) -> dict[str, Any]:
    monkeypatch.setenv("KIMI_BASE_URL", "https://api.kimi.com/coding/v1")
    config = subset.configuration("live")
    metadata = subset.metadata_for("live", config)
    metadata["source_sha256"] = "a" * 64
    metadata["execution_sha256"] = "b" * 64
    cases = [migrate(case)[0] for case in load_scenarios()]
    planned = {case.id: scenario_v21_hash(case) for case in cases}
    ledger = tmp_path / "shared-membership.json"
    clock = FrozenClock(datetime(2026, 10, 18, 1, tzinfo=UTC))
    budget = MemberBudget(ledger, "c21-synthetic-baseline", clock)
    budget.before_provider_request("probe")
    metadata.update(
        status="complete",
        run_id=budget.run_id,
        membership=budget.snapshot(),
        planned_contracts=planned,
        planned_contracts_sha256=canonical_hash(planned),
        member_ledger_identity=ledger_identity(ledger),
        scoring_contract_version=VERSION,
    )
    parent = {
        "metadata": deepcopy(metadata),
        "cases": [
            {
                "id": case.id,
                "category": case.category,
                "status": "passed" if "v3" in case.targets else "n/a on v3",
                "score": 1.0 if "v3" in case.targets else None,
                "scenario_contract_sha256": planned[case.id],
            }
            for case in cases
        ],
    }
    baseline = tmp_path / "baseline" / "baseline-v3-c2.1.json"
    write_json(baseline, parent)
    monkeypatch.setattr(subset, "metadata_for", lambda mode, config: deepcopy(metadata))
    monkeypatch.setattr(subset, "execution_digest", lambda: "b" * 64)
    monkeypatch.setattr(
        subset,
        "verify_source",
        lambda path: {
            "source_sha256": "a" * 64,
            "execution_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(subset, "MemberBudget", lambda path, run_id: budget)
    return {
        "parent": parent,
        "baseline": baseline,
        "ledger": ledger,
        "freeze": tmp_path / "freeze.json",
        "output": tmp_path / "port-subset",
        "budget": budget,
        "clock": clock,
        "metadata": metadata,
    }


def invoke(context: dict[str, Any], *, resume: bool = False) -> int:
    return subset.run(context["baseline"], context["ledger"], context["freeze"], context["output"], resume=resume)


def record(scenario: Any) -> dict[str, Any]:
    return {
        "id": scenario.id,
        "category": scenario.category,
        "status": "passed",
        "score": 1.0,
        "answers_full": ["完整合成回答"],
        "receipts_by_turn": [[]],
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "incomplete"),
        ("model", "other"),
        ("judge_model", "k3"),
        ("rubric_sha256", "changed"),
        ("source_sha256", "changed"),
        ("execution_sha256", "changed"),
        ("scoring_contract_version", "deterministic-eval-v2.2.0"),
        ("member_ledger_identity", "another-ledger"),
    ],
)
def test_preflight_rejects_invalid_baseline_without_constructing_provider(
    context: dict[str, Any], monkeypatch: Any, field: str, value: str
) -> None:
    parent = deepcopy(context["parent"])
    parent["metadata"][field] = value
    write_json(context["baseline"], parent)
    prepare = Mock(side_effect=AssertionError("provider construction must not happen"))
    monkeypatch.setattr(subset, "prepare", prepare)
    with pytest.raises(SystemExit, match="complete valid"):
        invoke(context)
    prepare.assert_not_called()


def test_preflight_requires_all_eighty_and_unchanged_scenario_contract(context: dict[str, Any]) -> None:
    parent = deepcopy(context["parent"])
    parent["cases"].pop()
    write_json(context["baseline"], parent)
    with pytest.raises(SystemExit):
        subset.preflight(context["baseline"], context["ledger"], context["freeze"])
    parent = deepcopy(context["parent"])
    parent["cases"][0]["scenario_contract_sha256"] = "changed"
    write_json(context["baseline"], parent)
    with pytest.raises(SystemExit):
        subset.preflight(context["baseline"], context["ledger"], context["freeze"])


def test_prepare_binds_single_evaluation_port_and_same_member_budget(context: dict[str, Any], monkeypatch: Any) -> None:
    monkeypatch.setenv("KIMI_API_KEY", "synthetic-only")
    monkeypatch.setenv("KIMI_MODEL", "k3")
    monkeypatch.delenv("MODELS_CONFIG", raising=False)
    monkeypatch.delenv("MINGJING_MODEL_PORT", raising=False)
    verify = Mock()
    monkeypatch.setattr(subset, "verify_local_postgres", verify)
    monkeypatch.setenv("CORE_TEST_DSN", "postgresql://core_test@127.0.0.1:55480/core_test_main")
    with pytest.raises(SystemExit, match="core_test_e1"):
        subset.prepare(context["budget"], context["parent"])
    verify.assert_not_called()
    monkeypatch.setenv("CORE_TEST_DSN", "postgresql://core_test@127.0.0.1:55480/core_test_e1")
    judge, target = subset.prepare(context["budget"], context["parent"])
    provider = target.observed.provider
    assert isinstance(provider, PortBackedModel)
    assert provider.role == "evaluation" and provider.port.stop_on_quota is True
    assert [handle.model for handle in provider.registry.resolve("evaluation")] == ["k3"]
    assert target.budget is judge.provider.budget is context["budget"]
    assert os_switches_off()
    target.close()


def os_switches_off() -> bool:
    import os

    return not os.getenv("MODELS_CONFIG") and os.getenv("MINGJING_MODEL_PORT") != "v2"


def stubs(context: dict[str, Any], monkeypatch: Any) -> tuple[Any, Any]:
    judge = SimpleNamespace(records=[])
    target = SimpleNamespace(close=Mock())
    monkeypatch.setattr(subset, "prepare", lambda budget, parent: (judge, target))
    return judge, target


def test_success_uses_ten_paired_cases_and_never_overwrites_baseline(context: dict[str, Any], monkeypatch: Any) -> None:
    judge, _ = stubs(context, monkeypatch)
    original = context["baseline"].read_bytes()
    identities: list[str] = []

    def evaluate(scenario: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        identities.append(scenario.id)
        context["budget"].before_provider_request("target")
        context["budget"].before_provider_request("judge")
        judge.records.append({"scenario_id": scenario.id, "answer": "完整合成回答"})
        return record(scenario)

    monkeypatch.setattr(subset, "evaluate_scenario", evaluate)
    assert invoke(context) == 0
    report = json.loads((context["output"] / subset.STATE_NAME).read_text(encoding="utf-8"))
    assert identities == list(subset.SUBSET_IDS)
    assert report["metadata"]["adapter"] == "ModelPort-v2/anthropic_messages"
    assert report["metadata"]["new_real_calls"] == 20
    assert report["metadata"]["membership"]["run_calls_by_role"] == {"target": 10, "judge": 10, "probe": 1}
    assert report["comparison"]["within_5pp_decline"] is True
    assert len(report["evidence_full"]) == 10
    assert context["baseline"].read_bytes() == original
    assert not list(context["output"].glob("baseline-v3*"))


def test_resume_reuses_completed_case_without_resetting_quota_recovery(
    context: dict[str, Any], monkeypatch: Any
) -> None:
    stubs(context, monkeypatch)
    calls: list[str] = []

    def evaluate(scenario: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(scenario.id)
        context["budget"].before_provider_request("target")
        if scenario.id == "T02" and calls.count("T02") == 1:
            context["budget"].record_stop("quota_5h", 403)
            raise ProviderStopped("quota_5h", "target", resume_at=context["budget"].snapshot()["resume_at"])
        context["budget"].before_provider_request("judge")
        return record(scenario)

    monkeypatch.setattr(subset, "evaluate_scenario", evaluate)
    assert invoke(context) == 3
    context["clock"].advance(timedelta(hours=5))
    assert invoke(context, resume=True) == 0
    assert calls.count("T01") == 1 and calls.count("T02") == 2
    report = json.loads((context["output"] / subset.STATE_NAME).read_text(encoding="utf-8"))
    assert report["metadata"]["new_real_calls"] == 21
    assert report["metadata"]["membership"]["auto_resumes"] == 1


def test_weekly_stop_is_saved_first_and_baseline_is_untouched(context: dict[str, Any], monkeypatch: Any) -> None:
    stubs(context, monkeypatch)
    original = context["baseline"].read_bytes()

    def evaluate(*args: Any, **kwargs: Any) -> dict[str, Any]:
        context["budget"].before_provider_request("target")
        context["budget"].record_stop("quota_weekly", 403)
        raise ProviderStopped("quota_weekly", "target", provider_http_status=403)

    monkeypatch.setattr(subset, "evaluate_scenario", evaluate)
    assert invoke(context) == 2
    assert (context["output"] / "port-subset-v21.md").read_text(encoding="utf-8").startswith("线上可能受影响")
    assert context["baseline"].read_bytes() == original


def test_interrupt_saves_evidence_and_actual_ledger_without_retry(context: dict[str, Any], monkeypatch: Any) -> None:
    judge, target = stubs(context, monkeypatch)

    def evaluate(*args: Any, **kwargs: Any) -> dict[str, Any]:
        context["budget"].before_provider_request("target")
        judge.records.append({"answer": "完整合成答复，等待复核"})
        raise KeyboardInterrupt

    monkeypatch.setattr(subset, "evaluate_scenario", evaluate)
    with pytest.raises(KeyboardInterrupt):
        invoke(context)
    report = json.loads((context["output"] / subset.STATE_NAME).read_text(encoding="utf-8"))
    assert report["metadata"]["status"] == "incomplete"
    assert report["metadata"]["execution_error_code"] == "KeyboardInterrupt"
    assert report["metadata"]["new_real_calls"] == 1
    assert report["evidence_full"] == judge.records
    target.close.assert_called_once()


def test_shared_batch_cooldown_prevents_any_new_request(context: dict[str, Any], monkeypatch: Any) -> None:
    stubs(context, monkeypatch)
    context["budget"].before_batch(["D02"])
    context["budget"].finish_batch()
    evaluate = Mock(side_effect=AssertionError("no request during cooldown"))
    monkeypatch.setattr(subset, "evaluate_scenario", evaluate)
    assert invoke(context) == 3
    evaluate.assert_not_called()
    assert context["budget"].snapshot()["run_calls_total"] == 1


def test_subset_resume_refuses_changed_baseline_or_cached_contract(context: dict[str, Any]) -> None:
    _, metadata, _ = subset.preflight(context["baseline"], context["ledger"], context["freeze"])
    cached = deepcopy(next(case for case in context["parent"]["cases"] if case["id"] == "T01"))
    report = {"metadata": deepcopy(metadata), "cases": [cached], "evidence_full": []}
    write_json(context["output"] / subset.STATE_NAME, report)
    changed = {**metadata, "baseline_sha256": "changed"}
    with pytest.raises(SystemExit, match="changed source"):
        subset.load_state(context["output"], changed, resume=True)
    report["cases"][0]["scenario_contract_sha256"] = "changed"
    write_json(context["output"] / subset.STATE_NAME, report)
    with pytest.raises(SystemExit, match="relabel"):
        subset.load_state(context["output"], metadata, resume=True)


def test_infrastructure_failure_is_incomplete_without_automatic_retry_or_comparison(
    context: dict[str, Any], monkeypatch: Any
) -> None:
    stubs(context, monkeypatch)
    identities: list[str] = []

    def evaluate(scenario: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        identities.append(scenario.id)
        context["budget"].before_provider_request("target")
        result = record(scenario)
        if scenario.id == "T01":
            result.update(status="failed", score=0.0, judge_error_code="ValueError")
        return result

    monkeypatch.setattr(subset, "evaluate_scenario", evaluate)
    assert invoke(context) == 2
    report = json.loads((context["output"] / subset.STATE_NAME).read_text(encoding="utf-8"))
    assert report["metadata"]["status"] == "incomplete"
    assert report["metadata"]["pending_scenario_ids"] == ["T01"]
    assert report["metadata"]["resume_at"] is None
    assert "comparison" not in report
    assert identities.count("T01") == 1

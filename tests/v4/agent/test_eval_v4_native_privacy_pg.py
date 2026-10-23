"""Privacy actions begin with real materialized dependencies, never empty seed shortcuts."""

import os
from pathlib import Path

import httpx
import pytest

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.source_withdrawal import SourceWithdrawalService
from mingjing_core.domain.contracts import RevisionConflict, ScopeError
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def target(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("native privacy acceptance forbids external HTTP and processes")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    monkeypatch.setattr("subprocess.run", reject)
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable loopback PostgreSQL")
    value = V4Target(dsn=dsn)
    try:
        yield value
    finally:
        value.close()


@pytest.mark.parametrize("identity", ["F01", "F03"])
def test_native_privacy_original_contracts_have_real_nonempty_initial_layers(target, identity):
    scenario = next(case for case in load_scenarios(ROOT / "tools/eval/scenarios") if case.id == identity)
    result = evaluate_scenario(execution_overlay(scenario), target, target_name="v4")
    assert result["status"] == "passed", result["failed_assertions"]
    initial = target.inspect_db()["run_meta"]["privacy_initial_layers"]
    if identity == "F01":
        assert initial == {"followup": 1, "profile_item": 1, "search_hit": 1, "embedding": 1}
        fact = target.repo.get(target.owner, "fact", target.bindings["interview"], include_deleted=True)
        assert fact["status"] == "deleted" and not fact.get("content")
    else:
        assert initial == {
            "fact": 1,
            "note": 1,
            "episode": 1,
            "thread_summary": 1,
            "run_event": 1,
            "run_step": 1,
            "embedding": 1,
        }


def test_source_delete_checks_scope_revision_receipt_and_notifies_real_revocation(target):
    target.reset({"synthetic": True, "_scenario_id": "source-delete-safety", "_scripted": []})
    repo = target.repo
    memory = MemoryService(repo)
    calls = []
    memory.on_revoke = lambda owner, facts, sources: calls.append((owner, facts, sources))
    source = memory.receive(
        target.owner, content="请记住，合成面试会在下周。", source_id="delete-source", channel="web"
    )
    service = SourceWithdrawalService(memory)
    with pytest.raises(ScopeError):
        service.delete("another-owner", "self", source["id"], expected_revision=source["revision"], request_id="delete")
    with pytest.raises(ScopeError):
        service.delete(
            target.owner, "another-subject", source["id"], expected_revision=source["revision"], request_id="delete"
        )
    with pytest.raises(RevisionConflict):
        service.delete(
            target.owner, "self", source["id"], expected_revision=source["revision"] + 1, request_id="delete"
        )
    assert repo.get(target.owner, "message", source["id"])["content"] == source["content"] and not calls
    args = dict(expected_revision=source["revision"], request_id="delete")
    first = service.delete(target.owner, "self", source["id"], **args)
    assert service.delete(target.owner, "self", source["id"], **args) == first
    assert len(calls) == 1 and calls[0][2] == [source["id"]]
    assert repo.is_revoked(target.owner, "message", source["id"])

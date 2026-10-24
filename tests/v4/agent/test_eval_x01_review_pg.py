"""Unchanged X01 contract observes existing P3 scheduling, never production P6."""

from __future__ import annotations

import os
import subprocess
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from psycopg import sql

from mingjing_core.agent.review import CriticVerdict
from tools.eval.contracts import scenario_contract_hash
from tools.eval.engine import evaluate_scenario
from tools.eval.judges import check_assertions
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_review_harness import DRAFT, critic_script, harness_evidence
from tools.eval.targets.v4_review_observations import review_counts, review_observations
from tools.eval.targets.v4_target import V4Target

ROOT = Path(__file__).resolve().parents[3]
ORIGINAL_HASH = "76a4343b8f5b28a9815c9d33e8b4ffac8805d1962fe21e3cf78948c68b35e15f"


def x01():
    return next(case for case in load_scenarios(ROOT / "tools/eval/scenarios") if case.id == "X01")


def seed_for(case):
    return {
        **case.seed.model_dump(mode="json"),
        "_scenario_id": case.id,
        "_scripted": [step.model_dump(exclude_none=True) for step in case.scripted],
    }


def test_overlay_preserves_original_contract_and_uses_only_declared_model_responses():
    original = x01()
    prepared = execution_overlay(original)
    assert scenario_contract_hash(original) == scenario_contract_hash(prepared) == ORIGINAL_HASH
    assert prepared.seed == original.seed and prepared.turns == original.turns
    assert execution_overlay(prepared) == prepared
    actions = [action.model_dump(exclude_none=True) for action in prepared.scripted[0].model]
    assert len(actions) == 2 and actions[0] == {"text": DRAFT}
    assert actions[1] == {"text": original.scripted[0].model[-1].text}
    responses = critic_script(seed_for(prepared))[0]["model"]
    for response, primary in zip(responses, actions, strict=True):
        assert CriticVerdict.parse(response["text"], primary["text"]).verdict == "revise"


@pytest.mark.parametrize("control", [["revise"], ["pass", "revise"], ["revise", "revise", "revise"]])
def test_harness_rejects_changed_original_controls(control):
    seed = seed_for(execution_overlay(x01()))
    seed["controls"]["critic_verdicts"] = control
    with pytest.raises(ValueError, match="original critic controls"):
        critic_script(seed)


class RecordingTarget(V4Target):
    def send(self, turn):
        self.last_result = super().send(turn)
        return self.last_result


@pytest.fixture(scope="module")
def completed():
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires explicit disposable loopback PG15")
    with pytest.MonkeyPatch.context() as patch:

        def forbidden(*args, **kwargs):
            raise AssertionError("X01 forbids provider/Feishu HTTP and child processes")

        patch.setattr(httpx.Client, "send", forbidden)
        patch.setattr(httpx.AsyncClient, "send", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        target = RecordingTarget(dsn=dsn)
        try:
            case = evaluate_scenario(execution_overlay(x01()), target, target_name="v4")
            assert case["status"] == "passed", case["failed_assertions"]
            yield target, case
        finally:
            target.close()


def test_original_x01_commits_one_real_revision_and_leaves_second_revise_unconsumed(
    completed,
):
    target, case = completed
    assert case["model_calls"] == 3
    assert target.port.calls == 2 and target.critic.calls == 1 and len(target.critic.actions) == 1
    observed = target.inspect_db()
    run = target.repo.fetch_run(target.owner, target.run_ids[-1])
    assert run["result"]["review"]["state"] == "revised"
    assert observed["run_meta"]["revision_count"] == observed["run_meta"]["critic_count"] == 1
    assert observed["run_meta"]["native_status"] == "succeeded"
    with target.repo.transaction(target.owner) as connection:
        kinds = connection.execute(
            sql.SQL("SELECT kind FROM {} WHERE owner=%s AND run_id=%s").format(target.repo.table("core_run_events")),
            (target.owner, run["id"]),
        ).fetchall()
    assert {"review", "text_reset", "final"} <= {row["kind"] for row in kinds}
    assert not {"critic.reviewed", "answer.revised"} & {row["kind"] for row in kinds}
    assert [item["name"] for item in review_observations(target.repo, target.owner, run)] == [
        "critic.reviewed",
        "answer.revised",
    ]
    evidence = target.case_evidence()["review_harness"]
    assert evidence["scope"] == "offline P3 review harness" and evidence["production_internal_critic"] is False
    assert evidence["completed_primary_steps"] == 2 and evidence["completed_critic_steps"] == 1
    assert "core_run_steps" in evidence["source_store"]
    checks = check_assertions({"db": [{"path": "run_meta.revision_count", "equals": 99}]}, target.last_result)
    assert checks and not any(check.passed for check in checks)


@pytest.mark.parametrize("change", ["owner", "epoch", "run", "operation"])
def test_review_aliases_cannot_borrow_other_run_identity(completed, change):
    target, _ = completed
    run = target.repo.fetch_run(target.owner, target.run_ids[-1])
    wrong = deepcopy(run)
    key = {
        "owner": "owner",
        "epoch": "retry_epoch",
        "run": "id",
        "operation": "operation_id",
    }[change]
    wrong[key] = run[key] + 1 if change == "epoch" else "another-synthetic-identity"
    assert review_observations(target.repo, target.owner, wrong) == []
    assert review_observations(target.repo, "another-owner", run) == []


TAMPERS = {
    "proof_hash": "UPDATE {entities} SET data=jsonb_set(data,'{{output_sha256}}','\"changed\"') "
    "WHERE owner=%s AND kind='runtime_step' AND data->>'stage'='agent_review'",
    "proof_epoch": "UPDATE {entities} SET data=jsonb_set(data,'{{epoch}}','99') "
    "WHERE owner=%s AND kind='runtime_step' AND data->>'stage'='agent_review'",
    "revision_failed": "UPDATE {steps} SET status='failed' WHERE owner=%s AND name='revision'",
    "reset_identity": "UPDATE {events} SET payload=jsonb_set(payload,'{{revision_id}}','\"old-epoch\"') "
    "WHERE owner=%s AND kind='text_reset'",
    "no_final_event": "DELETE FROM {events} WHERE owner=%s AND kind='final'",
    "no_review_event": "DELETE FROM {events} WHERE owner=%s AND kind='review'",
}


@pytest.mark.parametrize("change", TAMPERS)
def test_missing_or_corrupted_native_proof_never_generates_review_aliases(completed, change):
    target, _ = completed
    repo = target.repo
    run = repo.fetch_run(target.owner, target.run_ids[-1])
    with repo.transaction(target.owner) as connection:
        connection.execute("SAVEPOINT x01_negative")
        try:
            connection.execute(
                sql.SQL(TAMPERS[change]).format(
                    entities=repo.table("core_entities"),
                    steps=repo.table("core_run_steps"),
                    events=repo.table("core_run_events"),
                ),
                (target.owner,),
            )
            assert review_observations(repo, target.owner, run) == []
            if change == "revision_failed":
                assert review_counts(repo, target.owner, run)["revision_count"] == 0
        finally:
            connection.execute("ROLLBACK TO SAVEPOINT x01_negative")
    assert len(review_observations(repo, target.owner, run)) == 2


def test_a_live_port_cannot_be_reported_as_an_offline_review_harness(completed, monkeypatch):
    target, _ = completed
    monkeypatch.setattr(target.critic, "offline", False)
    with pytest.raises(ValueError, match="live model port"):
        harness_evidence(target)

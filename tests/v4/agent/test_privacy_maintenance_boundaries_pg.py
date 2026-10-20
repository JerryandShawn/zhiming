"""Retention scope excludes other owners' colliding entities, active work and Core v3."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.journal import Journal, input_fingerprint
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.privacy_maintenance import PrivacyMaintenance
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock
from tests.test_core_pg_channels import FixtureModel

from .test_agent_runtime_pg import invoke, queued
from .test_loop_cycle_support import ScriptedPort, answer
from .test_privacy_maintenance_pg import repository as source_repo_fixture


@pytest.fixture(name="boundary_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Any:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def age_run(repo: PostgresRepository, owner: str, ident: str) -> None:
    with repo.transaction(owner) as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET updated_at=%s WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
            (get_clock().now() - timedelta(days=31), owner, ident),
        )


def stored_steps(repo: PostgresRepository, owner: str, ident: str) -> list[dict[str, Any]]:
    with repo.transaction(owner) as connection:
        return connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND run_id=%s ORDER BY epoch,seq").format(
                repo.table("core_run_steps")
            ),
            (owner, ident),
        ).fetchall()


def test_cleanup_does_not_delete_other_owner_entity_even_when_ids_collide(boundary_repo: PostgresRepository) -> None:
    repo, run = boundary_repo, queued(boundary_repo)
    result, _ = invoke(repo, run, ScriptedPort([answer("合成甲方公开答案")]))
    step = next(row for row in repo.list("alice", "runtime_step") if row.get("run_id") == run["id"])
    # Entity IDs are owner-scoped. The collision is legal and must not let
    # one owner's maintenance selection erase the other owner's private body.
    repo.ensure_owner("bob")
    bob = repo.put(
        "bob",
        "runtime_step",
        step["id"],
        {"run_id": run["id"], "output": {"reasoning": "合成乙方保留正文"}},
        operation_id="bob-owned-colliding-step",
    )
    age_run(repo, "alice", run["id"])
    assert PrivacyMaintenance(repo).tick()["private_steps"] == 1
    assert repo.get("bob", "runtime_step", bob["id"]) == bob
    assert repo.get("alice", "runtime_step", step["id"], include_deleted=True)["status"] == "deleted"
    assert repo.fetch_run("alice", run["id"])["result"] == result


def test_old_running_v4_step_and_current_lease_are_preserved(boundary_repo: PostgresRepository) -> None:
    repo, run = boundary_repo, queued(boundary_repo)
    journal = Journal(repo, "alice")
    first = journal.next_or_replay(run, kind="model", input_fp=input_fingerprint("model", "", {}))
    journal.complete(first, {"text": "合成运行中输出", "reasoning": "合成仍在使用的推理"})
    age_run(repo, "alice", run["id"])
    before = stored_steps(repo, "alice", run["id"])
    assert PrivacyMaintenance(repo).tick()["private_steps"] == 0
    assert stored_steps(repo, "alice", run["id"]) == before
    current = repo.fetch_run("alice", run["id"])
    assert current["status"] == "running" and current["lease_token"] == run["lease_token"]
    assert "private_steps_expired_at" not in current["usage"].get("agent_runtime", {})


def test_core3_final_and_legacy_runtime_outputs_survive_thirty_day_policy(boundary_repo: PostgresRepository) -> None:
    repo = boundary_repo
    service = ConsultationService(repo, model=FixtureModel())
    run = service.submit(owner="alice", request_id="legacy-retention", message="合成学习安排", depth="fast")
    try:
        result = service.execute("alice", run["id"])
        assert result["schema_version"] == "core3.0" and result["validation"]["status"] == "validated"
        before = [row for row in repo.list("alice", "runtime_step") if row.get("run_id") == run["id"]]
        assert before
        age_run(repo, "alice", run["id"])
        assert PrivacyMaintenance(repo).tick()["private_steps"] == 0
        after = [row for row in repo.list("alice", "runtime_step") if row.get("run_id") == run["id"]]
        assert after == before and repo.fetch_run("alice", run["id"])["result"] == result
    finally:
        service.runtime.purge(run["id"], 0)

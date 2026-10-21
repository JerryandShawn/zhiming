"""Retention removes provider-private bodies without deleting published life history."""

from datetime import timedelta

import pytest
from psycopg import sql

from mingjing_core.application.privacy_maintenance import PrivacyMaintenance
from mingjing_core.application.threads import ThreadService
from mingjing_core.timekit.clock import get_clock

from .test_agent_runtime_pg import invoke, queued, repository_fixture
from .test_loop_cycle_support import ScriptedPort, answer


@pytest.fixture(name="retention_repo")
def repository(p2_repo, monkeypatch):
    yield from repository_fixture.__wrapped__(p2_repo, monkeypatch)


def test_private_thread_expires_automatically_and_never_expires_life(retention_repo):
    repo = retention_repo
    threads = ThreadService(repo)
    life = threads.create("alice", request_id="life")
    private = threads.create("alice", incognito=True, request_id="private")
    kept = threads.receive("alice", life["id"], "合成人生保留", request_id="life-source")
    hidden = threads.receive("alice", private["id"], "合成暂存到期", request_id="private-source")
    assert PrivacyMaintenance(repo).tick()["private_threads"] == 0
    get_clock().advance(timedelta(hours=24, seconds=1))
    assert PrivacyMaintenance(repo).tick()["private_threads"] == 1
    assert repo.get("alice", "message", kept["id"])["content"] == "合成人生保留"
    assert repo.get("alice", "message", hidden["id"], include_deleted=True)["status"] == "deleted"
    assert PrivacyMaintenance(repo).tick() == {"private_threads": 0, "reminders": 0, "private_steps": 0}


def test_thirty_day_step_cleanup_preserves_final_result_and_assistant(retention_repo):
    repo = retention_repo
    run = queued(repo)
    result, _ = invoke(repo, run, ScriptedPort([answer("合成公开答复")]))
    with repo.transaction("alice") as connection:
        connection.execute(sql.SQL("UPDATE {} SET updated_at=%s WHERE owner=%s AND id=%s").format(
            repo.table("core_runs")), (get_clock().now()-timedelta(days=31), "alice", run["id"]))
    assert PrivacyMaintenance(repo).tick()["private_steps"] == 1
    current = repo.fetch_run("alice", run["id"])
    assert current["result"] == result and current["status"] == "succeeded"
    assert repo.get("alice", "message", result["message_id"])["content"] == "合成公开答复"
    assert not [row for row in repo.list("alice", "runtime_step") if row.get("run_id") == run["id"]]
    with repo.transaction("alice") as connection:
        steps = connection.execute(sql.SQL("SELECT output FROM {} WHERE owner=%s AND run_id=%s").format(
            repo.table("core_run_steps")), ("alice", run["id"])).fetchall()
    assert steps and all(row["output"] is None for row in steps)
    assert PrivacyMaintenance(repo).tick()["private_steps"] == 0

"""A new single-write run must not downgrade after all local effect markers disappear."""

from collections.abc import Iterator

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_case_capability import KEY, case_effect_capability, pin_case_effect_capability
from mingjing_core.application.agent_case_effect_marker import MARKER, PROTOCOL, SCHEMA
from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.postgres import PostgresRepository

from .case_status_write_support import prepare_write
from .test_agent_runtime_pg import invoke
from .test_loop_cycle_case_versions_pg import selected_run
from .test_loop_cycle_support import ScriptedPort, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="loss_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def test_new_single_write_cannot_downgrade_when_effect_marker_and_protocol_are_all_lost(loss_repo, monkeypatch):
    prepared = prepare_write(loss_repo, monkeypatch)
    usage = loss_repo.fetch_run("alice", prepared.run["id"])["usage"]
    usage.pop(MARKER)
    usage.pop(PROTOCOL)
    with loss_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE id=%s").format(loss_repo.table("core_runs")),
            (Jsonb(usage), prepared.run["id"]),
        )
        removed = connection.execute(
            sql.SQL("DELETE FROM {} WHERE data->>'run_id'=%s AND data->>'schema'=%s").format(
                loss_repo.table("core_entities")
            ),
            (prepared.run["id"], SCHEMA),
        )
        assert removed.rowcount == 1
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()


def test_fresh_runtime_pins_capability_before_any_snapshot_or_journal(loss_repo, monkeypatch):
    original, observed = AgentSnapshotStore.load_or_build, []

    def before_snapshot(store, run, build):
        current = loss_repo.fetch_run("alice", run["id"])
        assert case_effect_capability(current) and current["state_version"] == {}
        with loss_repo.transaction("alice") as connection:
            assert not connection.execute(
                sql.SQL("SELECT 1 FROM {} WHERE run_id=%s").format(loss_repo.table("core_run_steps")), (run["id"],)
            ).fetchone()
        observed.append(current["usage"]["agent_runtime"][KEY])
        return original(store, run, build)

    monkeypatch.setattr(AgentSnapshotStore, "load_or_build", before_snapshot)
    run = selected_run(
        loss_repo, loss_repo.put("alice", "case", "synthetic-case", {"title": "合成事项"})["id"], "请看事项"
    )
    invoke(loss_repo, run, ScriptedPort([answer("合成答复")]))
    assert len(observed) == 1


@pytest.mark.parametrize("damage", ["invalid", "missing", "boolean_epoch"])
def test_resume_never_silently_replaces_damaged_or_missing_capability(loss_repo, monkeypatch, damage):
    prepared = prepare_write(loss_repo, monkeypatch)
    usage = loss_repo.fetch_run("alice", prepared.run["id"])["usage"]
    if damage == "missing":
        usage["agent_runtime"].pop(KEY)
    elif damage == "boolean_epoch":
        usage["agent_runtime"][KEY]["0"]["epoch"] = False
    else:
        usage["agent_runtime"][KEY]["0"]["protocol"] = "invalid"
    with loss_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE id=%s").format(loss_repo.table("core_runs")),
            (Jsonb(usage), prepared.run["id"]),
        )
    if damage != "missing":
        with pytest.raises(CoreError):
            pin_case_effect_capability(loss_repo, prepared.run)
    else:
        pin_case_effect_capability(loss_repo, prepared.run)
    assert loss_repo.fetch_run("alice", prepared.run["id"])["usage"] == usage


@pytest.mark.parametrize("deleted", [False, True])
def test_existing_initial_snapshot_even_deleted_prevents_capability_backfill(loss_repo, monkeypatch, deleted):
    prepared = prepare_write(loss_repo, monkeypatch)
    usage = loss_repo.fetch_run("alice", prepared.run["id"])["usage"]
    usage["agent_runtime"].pop(KEY)
    with loss_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s,state_version='{{}}' WHERE id=%s").format(loss_repo.table("core_runs")),
            (Jsonb(usage), prepared.run["id"]),
        )
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE run_id=%s").format(loss_repo.table("core_run_steps")), (prepared.run["id"],)
        )
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE data->>'run_id'=%s AND data->>'stage'='agent_model_request'").format(
                loss_repo.table("core_entities")
            ),
            (prepared.run["id"],),
        )
        if deleted:
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET status='deleted' WHERE data->>'run_id'=%s AND data->>'stage'='agent_initial_context'"
                ).format(loss_repo.table("core_entities")),
                (prepared.run["id"],),
            )
    pin_case_effect_capability(loss_repo, prepared.run)
    assert KEY not in loss_repo.fetch_run("alice", prepared.run["id"])["usage"]["agent_runtime"]

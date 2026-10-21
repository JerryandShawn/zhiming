"""An unversioned component can replay, while damaged Runtime proof cannot opt out."""

from collections.abc import Iterator

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_pending_effects import pending_case_receipts
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_agent_runtime_pg import invoke
from .test_loop_cycle_support import ScriptedPort, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .tool_effect_recovery_support import CrashBeforeAcknowledgement, prepare_intent, step_row


@pytest.fixture(name="direct_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("witness", ["pin", "model", "initial", "deleted_initial", "old_epoch_model"])
def test_any_real_runtime_witness_prevents_unversioned_direct_downgrade(direct_repo, monkeypatch, witness):
    intent = prepare_intent(direct_repo, "case_update")
    crash = CrashBeforeAcknowledgement(direct_repo, intent.name, monkeypatch)
    port = ScriptedPort([answer("", [ToolCall("update", intent.name, intent.arguments)])])
    with pytest.raises(SystemExit):
        invoke(direct_repo, intent.run, port)
    current = direct_repo.fetch_run("alice", intent.run["id"])
    usage = dict(current["usage"])
    if witness != "pin":
        usage.pop("agent_runtime")
    with direct_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET state_version='{{}}'::jsonb,usage=%s WHERE id=%s").format(
                direct_repo.table("core_runs")
            ),
            (Jsonb(usage), intent.run["id"]),
        )
        if witness not in {"model", "old_epoch_model"}:
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE run_id=%s AND kind='model'").format(direct_repo.table("core_run_steps")),
                (intent.run["id"],),
            )
        elif witness == "old_epoch_model":
            connection.execute(
                sql.SQL("UPDATE {} SET epoch=1 WHERE run_id=%s AND kind='model'").format(
                    direct_repo.table("core_run_steps")
                ),
                (intent.run["id"],),
            )
        keep_initial = witness in {"initial", "deleted_initial"}
        connection.execute(
            sql.SQL(
                "DELETE FROM {} WHERE kind='runtime_step' AND data->>'run_id'=%s "
                "AND (data->>'stage'='agent_model_request' OR (data->>'stage'='agent_initial_context' AND NOT %s))"
            ).format(direct_repo.table("core_entities")),
            (intent.run["id"], keep_initial),
        )
        if witness == "deleted_initial":
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET status='deleted' WHERE kind='runtime_step' AND data->>'run_id'=%s "
                    "AND data->>'stage'='agent_initial_context'"
                ).format(direct_repo.table("core_entities")),
                (intent.run["id"],),
            )
    with pytest.raises(CoreError):
        pending_case_receipts(direct_repo, direct_repo.fetch_run("alice", intent.run["id"]))
    assert step_row(direct_repo, crash.step)["status"] == "started"
    assert direct_repo.fetch_run("alice", intent.run["id"])["result"] is None

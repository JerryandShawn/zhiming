"""The second committed effect may be recovered without inventing its Journal ack."""

import copy
from collections.abc import Iterator

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.journal import Journal
from mingjing_core.application.agent_case_effect_marker import MARKER, PROTOCOL, SCHEMA
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_agent_runtime_pg import invoke
from .test_loop_cycle_support import ScriptedPort, answer, modify
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .tool_effect_recovery_support import (
    business_state,
    externally_committed,
    mutation_row,
    operation_rows,
    prepare_intent,
    step_row,
)


@pytest.fixture(name="pending_chain_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def crash_second_effect(repo, monkeypatch):
    original, captured = Journal.complete, []

    def intercept(journal, step, output, *args, **kwargs):
        if step.kind == "tool" and step.name == "case_update" and output.get("receipt", {}).get("revision") == 3:
            externally_committed(repo, step, output["receipt"])
            captured.append((step, copy.deepcopy(output)))
            raise SystemExit("second-real-effect-before-ack")
        return original(journal, step, output, *args, **kwargs)

    monkeypatch.setattr(Journal, "complete", intercept)
    return captured, original


def prepare_pending_chain(repo, monkeypatch, same_response=True):
    intent = prepare_intent(repo, "case_update")
    first = ToolCall("goal", "case_update", intent.arguments)
    second = ToolCall("close", "case_update", dict(intent.arguments, expected_revision=2, changes={"status": "closed"}))
    responses = [answer("", [first, second])] if same_response else [answer("", [first]), answer("", [second])]
    captured, original = crash_second_effect(repo, monkeypatch)
    with pytest.raises(SystemExit, match="second-real-effect-before-ack"):
        invoke(repo, intent.run, ScriptedPort(responses))
    assert len(captured) == 1
    step, output = captured[0]
    monkeypatch.setattr(Journal, "complete", original)
    return intent, step, output


def reclaim(repo, run):
    modify(repo, run, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", run["id"], lease_seconds=150)
    assert reclaimed["retry_epoch"] == 0 and reclaimed["lease_token"] != run["lease_token"]
    return reclaimed


@pytest.mark.parametrize("same_response", [True, False])
def test_second_effect_reclaims_same_epoch_without_rewriting_proofs_or_duplicate_revision(
    pending_chain_repo, monkeypatch, same_response
):
    repo = pending_chain_repo
    intent, step, output = prepare_pending_chain(repo, monkeypatch, same_response)
    before, mutation, operations = business_state(repo), mutation_row(repo, step), operation_rows(repo, step)
    proofs = [row for row in repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA]
    initial = repo.get("alice", "runtime_step", f"{intent.run['id']}:e0:agent_initial_context")
    with repo.transaction("alice") as connection:
        prefix = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE run_id=%s AND seq<%s ORDER BY seq").format(repo.table("core_run_steps")),
            (step.run_id, step.seq),
        ).fetchall()
    assert len(proofs) == 2 and step_row(repo, step)["status"] == "started"
    reclaimed = reclaim(repo, intent.run)
    resumed = ScriptedPort([answer("恢复多写事项〔e1〕")])
    result, _ = invoke(repo, reclaimed, resumed)
    assert result["text"] == "恢复多写事项〔e1〕" and len(resumed.requests) == 1
    assert (
        business_state(repo) == before
        and mutation_row(repo, step) == mutation
        and operation_rows(repo, step) == operations
    )
    assert [row for row in repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA] == proofs
    assert step_row(repo, step)["status"] == "completed" and step_row(repo, step)["output"] == output
    assert repo.get("alice", "runtime_step", initial["id"]) == initial
    with repo.transaction("alice") as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT * FROM {} WHERE run_id=%s AND seq<%s ORDER BY seq").format(
                    repo.table("core_run_steps")
                ),
                (step.run_id, step.seq),
            ).fetchall()
            == prefix
        )


def damage_pending(repo, intent, step, damage):
    with repo.transaction("alice") as connection:
        if damage in {"first_proof", "last_proof", "all_new_proof"}:
            clause = "" if damage == "all_new_proof" else " AND data->>'seq'=%s"
            params = (intent.run["id"], SCHEMA) + (() if not clause else (str(2 if damage == "first_proof" else 3),))
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE data->>'run_id'=%s AND data->>'schema'=%s" + clause).format(
                    repo.table("core_entities")
                ),
                params,
            )
        if damage in {"marker", "protocol", "all_new_proof"}:
            usage = repo.fetch_run("alice", intent.run["id"])["usage"]
            usage.pop(PROTOCOL if damage == "protocol" else MARKER)
            if damage == "all_new_proof":
                usage.pop(PROTOCOL)
            connection.execute(
                sql.SQL("UPDATE {} SET usage=%s WHERE id=%s").format(repo.table("core_runs")),
                (Jsonb(usage), intent.run["id"]),
            )
        elif damage == "model":
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE run_id=%s AND kind='model'").format(repo.table("core_run_steps")),
                (step.run_id,),
            )
        elif damage == "pending_output":
            connection.execute(
                sql.SQL("UPDATE {} SET output='{{}}' WHERE run_id=%s AND seq=%s").format(repo.table("core_run_steps")),
                (step.run_id, step.seq),
            )
        elif damage == "external_same_body":
            row = repo.get("alice", "case", intent.old["id"])
            repo.update("alice", "case", row["id"], {"title": row["title"]}, expected_revision=row["revision"])
        elif damage == "withdrawal":
            repo.revoke(
                connection, "alice", "message", intent.run["request"]["source_message_id"], "synthetic-withdrawal"
            )


@pytest.mark.parametrize(
    "damage",
    [
        "first_proof",
        "last_proof",
        "marker",
        "protocol",
        "all_new_proof",
        "model",
        "pending_output",
        "external_same_body",
        "withdrawal",
    ],
)
def test_broken_pending_chain_never_replays_or_calls_a_new_model(pending_chain_repo, monkeypatch, damage):
    repo = pending_chain_repo
    intent, step, _ = prepare_pending_chain(repo, monkeypatch)
    damage_pending(repo, intent, step, damage)
    before = business_state(repo)
    run, denied = reclaim(repo, intent.run), ScriptedPort([])
    with pytest.raises(CoreError):
        invoke(repo, run, denied)
    assert denied.requests == [] and business_state(repo) == before
    assert step_row(repo, step)["status"] == "started"
    assert repo.fetch_run("alice", run["id"])["result"] is None

"""Legacy proof compatibility, mutation replay and new evidence rollback are explicit."""

from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.journal import Journal
from mingjing_core.agent.toolkit import ToolContext, ToolRegistry
from mingjing_core.application import agent_case_effect_records, agent_runtime_state, agent_tools_cases
from mingjing_core.application.agent_case_capability import KEY as CAPABILITY_KEY
from mingjing_core.application.agent_case_effect_marker import MARKER, SCHEMA
from mingjing_core.application.agent_pending_effects import _initial
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .case_effect_chain_support import prepare_chain
from .case_status_write_support import prepare_write
from .test_agent_runtime_pg import invoke
from .test_case_index_lineage_pg import existing_case
from .test_loop_cycle_case_versions_pg import selected_run
from .test_loop_cycle_support import ScriptedPort, answer, modify
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .tool_effect_recovery_support import CrashBeforeAcknowledgement, business_state, prepare_intent, step_row


@pytest.fixture(name="effect_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def legacy_writer(service: Any, args: dict, ctx: ToolContext, before: dict, payload: dict) -> dict:
    result = service.repo.update(
        ctx.owner,
        "case",
        before["id"],
        payload,
        expected_revision=before["revision"],
        operation_id=ctx.operation_id + ":case",
    )
    return {"write_status": "saved", "kind": "case", "id": result["id"], "revision": result["revision"]}


def install_legacy_runtime(monkeypatch):
    # Emulate both old writer and old initial pin; a new Runtime must not pretend
    # its omitted evidence is legacy merely because the writer was monkeypatched.
    monkeypatch.setattr(agent_tools_cases, "update_with_evidence", legacy_writer)
    monkeypatch.setattr(agent_runtime_state, "pin_case_effect_capability", lambda *args: None)


def test_old_protocol_single_write_remains_compatible_without_fabricating_evidence(effect_repo, monkeypatch):
    # This seam is the exact old real-PG update operation; no receipt/entity is faked.
    install_legacy_runtime(monkeypatch)
    prepared = prepare_write(effect_repo, monkeypatch)
    assert MARKER not in effect_repo.fetch_run("alice", prepared.run["id"])["usage"]
    assert not [row for row in effect_repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA]
    assert prepared.finish()["text"] == "事项状态已更新〔e1〕"


def test_old_protocol_multi_write_still_refuses_missing_historical_evidence(effect_repo, monkeypatch):
    install_legacy_runtime(monkeypatch)
    prepared = prepare_chain(effect_repo, monkeypatch)
    with pytest.raises(CoreError):
        prepared.finish()
    assert MARKER not in effect_repo.fetch_run("alice", prepared.run["id"])["usage"]
    prepared.unpublished()


def test_old_protocol_exact_single_started_effect_still_recovers_without_new_evidence(effect_repo, monkeypatch):
    intent = prepare_intent(effect_repo, "case_update")
    first = ScriptedPort([answer("", [ToolCall("change", intent.name, intent.arguments)])])
    with monkeypatch.context() as old:
        install_legacy_runtime(old)
        crash = CrashBeforeAcknowledgement(effect_repo, intent.name, old)
        with pytest.raises(SystemExit):
            invoke(effect_repo, intent.run, first)
    before = business_state(effect_repo)
    assert MARKER not in effect_repo.fetch_run("alice", intent.run["id"])["usage"]
    assert not [row for row in effect_repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA]
    modify(effect_repo, intent.run, "lease_until=now()-interval '1 second'")
    run = effect_repo.claim_run("alice", intent.run["id"], lease_seconds=150)
    resumed = ScriptedPort([answer("旧单写恢复〔e1〕")])
    result, _ = invoke(effect_repo, run, resumed)
    assert result["text"] == "旧单写恢复〔e1〕" and len(resumed.requests) == 1
    assert business_state(effect_repo) == before and step_row(effect_repo, crash.step)["status"] == "completed"
    assert CAPABILITY_KEY not in effect_repo.fetch_run("alice", run["id"])["usage"]["agent_runtime"]


@pytest.mark.parametrize("remove", [False, True])
def test_mutation_replay_never_recreates_before_or_changes_existing_proof(effect_repo, monkeypatch, remove):
    prepared = prepare_write(effect_repo, monkeypatch)
    record = next(row for row in effect_repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA)
    base = _initial(effect_repo, prepared.run)
    with effect_repo.transaction("alice") as connection:
        step = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE run_id=%s AND seq=2").format(effect_repo.table("core_run_steps")),
            (prepared.run["id"],),
        ).fetchone()
        if remove:
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE id=%s").format(effect_repo.table("core_entities")), (record["id"],)
            )
    ctx = ToolContext(
        "alice",
        prepared.run["id"],
        "self",
        0,
        2,
        prepared.run["lease_token"],
        "case_update",
        step["input_fp"],
        "life:self",
        source_ids=(prepared.run["request"]["source_message_id"],),
        case_ids=(prepared.case["id"],),
        source_versions=base.injected_versions,
    )
    arguments = record["output"]["arguments"]
    result = ToolRegistry(AgentToolsService(effect_repo)).execute("case_update", arguments, ctx)
    assert result.ok and result.receipt == record["output"]["receipt"]
    assert effect_repo.get("alice", "case", prepared.case["id"])["revision"] == 2
    if remove:
        assert not [row for row in effect_repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA]
        with pytest.raises(CoreError):
            prepared.finish()
    else:
        assert effect_repo.get("alice", "runtime_step", record["id"]) == record
        assert prepared.finish()["text"] == "事项状态已更新〔e1〕"


@pytest.mark.parametrize("failure", ["record", "marker", "size"])
def test_private_proof_failure_rolls_back_the_real_case_and_operation(effect_repo, monkeypatch, failure):
    case, _ = existing_case(effect_repo)
    run = selected_run(effect_repo, case["id"], "请关闭合成事项")
    service = AgentToolsService(effect_repo)
    registry, journal = ToolRegistry(service), Journal(effect_repo, "alice")
    args = {
        "id": case["id"],
        "expected_revision": 1,
        "message_id": run["request"]["source_message_id"],
        "quote": run["request"]["message"],
        "changes": {"status": "closed"},
    }
    step = journal.next_or_replay(
        run, kind="tool", name="case_update", input_fp=registry.fingerprint("case_update", args)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(args["message_id"],), case_ids=(case["id"],))
    observed, original_put = [], effect_repo.put

    def broken_put(owner, kind, ident, data, **kwargs):
        if kind == "runtime_step" and data.get("schema") == SCHEMA:
            observed.append(effect_repo.get("alice", "case", case["id"])["revision"])
            raise EvidenceError("synthetic record failure")
        return original_put(owner, kind, ident, data, **kwargs)

    if failure == "record":
        monkeypatch.setattr(effect_repo, "put", broken_put)
    elif failure == "marker":

        def broken_marker(*args, **kwargs):
            observed.append(effect_repo.get("alice", "case", case["id"])["revision"])
            raise EvidenceError("synthetic marker failure")

        monkeypatch.setattr(agent_case_effect_records, "mark_effect", broken_marker)
    else:
        monkeypatch.setattr(agent_case_effect_records, "MAX_EFFECT_BYTES", 10)
    result = registry.execute("case_update", args, ctx)
    assert not result.ok and effect_repo.get("alice", "case", case["id"]) == case
    assert observed == ([] if failure == "size" else [2])
    assert MARKER not in effect_repo.fetch_run("alice", run["id"])["usage"]
    assert not [row for row in effect_repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA]
    with effect_repo.transaction("alice") as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {} WHERE operation_id=%s").format(
                    effect_repo.table("core_operations")
                ),
                (ctx.operation_id + ":case",),
            ).fetchone()["n"]
            == 0
        )

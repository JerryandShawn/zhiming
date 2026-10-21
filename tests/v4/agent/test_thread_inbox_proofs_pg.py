"""Real journals, request ledger and final commit prove supplemental input adoption."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_tokens import apply_token_budget
from mingjing_core.agent.context_types import BudgetPolicy, ContextItem, ContextLayer
from mingjing_core.agent.journal import Journal, input_fingerprint
from mingjing_core.agent.loop_codec import assistant_output
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.thread_inbox import ThreadInbox
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_thread_inbox_pg import ingress, repository_fixture, set_runtime, submit  # noqa: F401


def pending(repo: PostgresRepository) -> tuple[Any, ...]:
    set_runtime(repo, "v4")
    service, thread = ingress(repo)
    parent = repo.claim_run("alice", submit(service, thread, "合成原始问题")["id"])
    engine = ContextEngine(MemoryService(repo), "合成入站测试", clock=get_clock(), token_meter=SyntheticMeter())
    frozen = AgentSnapshotStore(repo).load_or_build(
        parent, lambda: engine.build("alice", parent["request"]["source_message_id"], run_context=parent)
    )
    fallback = submit(service, thread, "合成补充原话")
    claim = ThreadInbox(repo).claim(parent, phase="before_model", iteration=1)[0]
    return parent, fallback, claim, frozen


def model_step(repo: PostgresRepository, parent: dict, claim: Any, frozen: Any) -> tuple[Any, dict, ScriptedPort]:
    versions = dict(frozen.injected_versions, **claim.versions)
    repo.set_run_dependencies("alice", parent["id"], versions, parent["lease_token"])
    base = tuple(layer for layer in frozen.budget.layers if layer.name != "CYCLE")
    additions = ContextLayer(
        "CYCLE",
        tuple(ContextItem("inbox:" + str(i), (message,), True) for i, message in enumerate(claim.user_messages)),
    )
    budget = apply_token_budget((*base, additions), (), meter=SyntheticMeter(), policy=BudgetPolicy())
    identity = dict(
        messages=[asdict(message) for message in budget.messages],
        tools=[],
        tool_choice="auto",
        source_versions=versions,
    )
    journal = Journal(repo, "alice")
    step = journal.next_or_replay(parent, kind="model", name="", input_fp=input_fingerprint("model", "", identity))
    ledger = RequestLedger(repo, SyntheticMeter(), offline=True)
    ledger.reserve(step, frozen, budget, "auto", versions)
    port = ScriptedPort([answer("合成已采用补充")])
    response = port.complete(list(budget.messages), tools=[], tool_choice="auto")
    completed = journal.complete(step, assistant_output(response), response.usage)
    ledger.completed(completed)
    return completed, versions, port


def replace_lease(repo: PostgresRepository, run: dict) -> dict:
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE id=%s").format(repo.table("core_runs")),
            (run["id"],),
        )
    return repo.claim_run("alice", run["id"])


def test_actual_model_and_commit_are_both_required_before_canceling_fallback(inbox_repo: PostgresRepository) -> None:
    repo = inbox_repo
    parent, fallback, claim, frozen = pending(repo)
    completed, versions, port = model_step(repo, parent, claim, frozen)
    inbox = ThreadInbox(repo)
    assert inbox.authorized_source_ids(parent) == ()
    inbox.ack(parent, claim, model_seq=completed.seq)
    assert inbox.authorized_source_ids(parent) == tuple(key[8:] for key in claim.versions)
    assert inbox.recover("alice") == {"queued": 0, "consumed": 0, "revoked": 0}
    AgentFinalizer(repo).finalize(
        parent,
        text="合成已采用补充",
        alias_map=frozen.alias_map,
        versions=versions,
        snapshot_revision=frozen.snapshot_revision,
    )
    assert inbox.recover("alice") == {"queued": 0, "consumed": 1, "revoked": 0}
    assert repo.fetch_run("alice", fallback["id"])["status"] == "cancelled"
    assert inbox.recover("alice") == {"queued": 0, "consumed": 0, "revoked": 0} and len(port.requests) == 1


def test_new_authoritative_lease_reclaims_uncompleted_input_with_new_token(inbox_repo: PostgresRepository) -> None:
    parent, fallback, claim, _ = pending(inbox_repo)
    new = replace_lease(inbox_repo, parent)
    resumed = ThreadInbox(inbox_repo).claim(new, phase="before_model", iteration=1)
    assert len(resumed) == 1 and resumed[0].token != claim.token
    with pytest.raises(LeaseConflict):
        ThreadInbox(inbox_repo).ack(parent, claim, model_seq=1)
    assert ThreadInbox(inbox_repo).authorized_source_ids(new) == ()
    inbox_repo.fail_run("alice", new["id"], "合成未完成", new["lease_token"])
    assert ThreadInbox(inbox_repo).recover("alice")["queued"] == 1
    assert inbox_repo.fetch_run("alice", fallback["id"])["status"] == "queued"


def test_new_lease_recovers_ack_only_from_completed_canonical_model_snapshot(inbox_repo: PostgresRepository) -> None:
    parent, fallback, claim, frozen = pending(inbox_repo)
    _, versions, port = model_step(inbox_repo, parent, claim, frozen)
    new = replace_lease(inbox_repo, parent)
    assert ThreadInbox(inbox_repo).claim(new, phase="before_model", iteration=1) == ()
    assert ThreadInbox(inbox_repo).authorized_source_ids(new) == tuple(key[8:] for key in claim.versions)
    AgentFinalizer(inbox_repo).finalize(
        new,
        text="合成恢复提交",
        alias_map=frozen.alias_map,
        versions=versions,
        snapshot_revision=frozen.snapshot_revision,
    )
    assert ThreadInbox(inbox_repo).recover("alice")["consumed"] == 1 and len(port.requests) == 1
    assert inbox_repo.fetch_run("alice", fallback["id"])["status"] == "cancelled"


def test_corrupted_request_hash_cannot_authorize_sources_or_consume_fallback(inbox_repo: PostgresRepository) -> None:
    parent, _, claim, frozen = pending(inbox_repo)
    completed, _, _ = model_step(inbox_repo, parent, claim, frozen)
    inbox = ThreadInbox(inbox_repo)
    inbox.ack(parent, claim, model_seq=completed.seq)
    row = inbox_repo.get("alice", "runtime_step", RequestLedger._id(parent["id"], 0, completed.seq))
    inbox_repo.update(
        "alice", "runtime_step", row["id"], {"output_sha256": "0" * 64}, expected_revision=row["revision"]
    )
    with pytest.raises(EvidenceError):
        inbox.authorized_source_ids(parent)
    inbox_repo.fail_run("alice", parent["id"], "合成快照失效", parent["lease_token"])
    assert inbox.recover("alice")["queued"] == 1

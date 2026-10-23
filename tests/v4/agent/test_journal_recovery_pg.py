"""Real tool effects, lease reclaim and privacy withdrawal bound journal replay."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.journal import Journal, JournalStep, input_fingerprint
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_journal_pg import configure_repo, modify_run, new_run, rows


@pytest.fixture(name="journal_repo")
def recovery_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return configure_repo(p2_repo, monkeypatch)


def reclaim(repo: PostgresRepository, run: dict[str, Any]) -> dict[str, Any]:
    modify_run(repo, run, "lease_until=now()-interval '1 second'")
    assert repo.recover_runs("alice") == 1
    return repo.claim_run("alice", run["id"])


def mutation_count(repo: PostgresRepository) -> int:
    with repo.transaction("alice") as connection:
        return connection.execute(
            sql.SQL("SELECT count(*) AS count FROM {} WHERE owner='alice'").format(repo.table("core_mutation_requests"))
        ).fetchone()["count"]


def save_once(
    repo: PostgresRepository, source: dict[str, Any], step: JournalStep, executed: list[str]
) -> dict[str, Any]:
    memory = MemoryService(repo)

    def effect() -> dict[str, Any]:
        executed.append(step.operation_id)
        fact = memory.save_fact(
            "alice", "self", source["id"], "我不能上夜班", "constraint", operation_id=step.operation_id
        )
        return {key: fact[key] for key in ("id", "revision", "write_status")}

    return repo.mutation_request(
        "alice", "memory_write", step.operation_id, {"source_message_id": source["id"], "quote": "我不能上夜班"}, effect
    )


@pytest.mark.parametrize("window", ["before_effect", "after_effect", "after_complete"])
def test_tool_crash_windows_replay_one_real_fact_and_receipt(journal_repo: PostgresRepository, window: str) -> None:
    repo = journal_repo
    source = MemoryService(repo).receive("alice", content="请记住，我不能上夜班", source_id="original")
    run = new_run(repo)
    journal = Journal(repo, "alice")
    digest = input_fingerprint("tool", "memory_write", {"source": source["id"], "version": source["revision"]})
    step = journal.next_or_replay(run, kind="tool", name="memory_write", input_fp=digest)
    executed = []
    with pytest.raises(SystemExit, match="SYNTHETIC_CRASH"):
        if window != "before_effect":
            receipt = save_once(repo, source, step, executed)
            if window == "after_complete":
                journal.complete(step, {"ok": True, "receipt": receipt}, {"actual_input_tokens": None})
        raise SystemExit("SYNTHETIC_CRASH")
    resumed = reclaim(repo, run)
    replay_journal = Journal(repo, "alice")
    replay = replay_journal.next_or_replay(resumed, kind="tool", name="memory_write", input_fp=digest)
    assert replay.operation_id == step.operation_id and resumed["lease_token"] != run["lease_token"]
    if not replay.completed:
        receipt = save_once(repo, source, replay, executed)
        replay = replay_journal.complete(replay, {"ok": True, "receipt": receipt}, {"actual_input_tokens": None})
    assert replay.completed and replay.output["receipt"]["write_status"] == "saved"
    assert len(executed) == mutation_count(repo) == len(MemoryService(repo).facts("alice")) == 1
    assert len(rows(repo)) == 1 and repo.fetch_run("alice", run["id"])["calls"] == 0
    final = Journal(repo, "alice").next_or_replay(resumed, kind="tool", name="memory_write", input_fp=digest)
    assert final.completed and final.output == replay.output


def test_outer_transaction_rollback_removes_effect_receipt_and_step(journal_repo: PostgresRepository) -> None:
    repo = journal_repo
    source = MemoryService(repo).receive("alice", content="我不能上夜班", source_id="original")
    run = new_run(repo)
    before = repo.get_revision("alice")
    with pytest.raises(SystemExit, match="SYNTHETIC_ROLLBACK"), repo.transaction("alice"):
        journal = Journal(repo, "alice")
        step = journal.next_or_replay(run, kind="tool", name="memory_write", input_fp="a" * 64)
        receipt = save_once(repo, source, step, [])
        journal.complete(step, {"ok": True, "receipt": receipt})
        raise SystemExit("SYNTHETIC_ROLLBACK")
    assert rows(repo) == [] and mutation_count(repo) == 0 and MemoryService(repo).facts("alice") == []
    assert repo.get_revision("alice") == before
    assert Journal(repo, "alice").next_or_replay(run, kind="tool", name="memory_write", input_fp="a" * 64).seq == 1


def test_reclaimed_worker_cannot_complete_but_current_lease_can(journal_repo: PostgresRepository) -> None:
    repo = journal_repo
    run = new_run(repo)
    old = Journal(repo, "alice")
    pending = old.next_or_replay(run, kind="model", input_fp="a" * 64)
    resumed = reclaim(repo, run)
    with pytest.raises(LeaseConflict):
        old.complete(pending, {"text": "旧worker迟到"})
    current = Journal(repo, "alice")
    step = current.next_or_replay(resumed, kind="model", input_fp="a" * 64)
    assert step.operation_id == pending.operation_id and not step.completed
    assert current.complete(step, {"text": "当前worker"}).completed
    assert len(rows(repo)) == 1


def test_real_source_withdrawal_erases_output_and_prevents_resurrection(journal_repo: PostgresRepository) -> None:
    repo = journal_repo
    memory = MemoryService(repo)
    source = memory.receive("alice", content="请记住，我不能上夜班", source_id="original")
    fact = memory.save_fact("alice", "self", source["id"], "我不能上夜班", "constraint")
    run = new_run(repo)
    repo.set_run_dependencies("alice", run["id"], {"fact:" + fact["id"]: fact["revision"]}, run["lease_token"])
    journal = Journal(repo, "alice")
    pending = journal.next_or_replay(run, kind="model", input_fp="a" * 64)
    completed = journal.complete(pending, {"text": "引用合成约束的回答"})
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    persisted = rows(repo)[0]
    assert persisted["status"] == "completed" and persisted["output"] is None
    assert persisted["error_code"] == "SOURCE_REVOKED"
    with pytest.raises(LeaseConflict):
        Journal(repo, "alice").next_or_replay(run, kind="model", input_fp="a" * 64)
    with pytest.raises(LeaseConflict):
        journal.complete(completed, completed.output)
    assert rows(repo)[0]["output"] is None


@pytest.mark.parametrize("error_code", ["SOURCE_REVOKED", None])
def test_completed_metadata_without_body_is_never_replayed_or_repopulated(
    journal_repo: PostgresRepository, error_code: str | None
) -> None:
    repo = journal_repo
    run = new_run(repo)
    journal = Journal(repo, "alice")
    step = journal.next_or_replay(run, kind="model", input_fp="a" * 64)
    journal.complete(step, {"text": "将被清理的合成正文"})
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET output=NULL,error_code=%s WHERE run_id=%s").format(repo.table("core_run_steps")),
            (error_code, run["id"]),
        )
    with pytest.raises(EvidenceError, match="不能恢复"):
        Journal(repo, "alice").next_or_replay(run, kind="model", input_fp="a" * 64)
    with pytest.raises(EvidenceError, match="不能恢复"):
        journal.complete(step, {"text": "不能复活"})
    assert rows(repo)[0]["output"] is None


@pytest.mark.parametrize("changed", [False, True])
def test_two_connection_traversals_share_one_identity_and_reject_conflicts(
    journal_repo: PostgresRepository, changed: bool
) -> None:
    repo = journal_repo
    run = new_run(repo)
    barrier = threading.Barrier(2)

    def start(index: int) -> JournalStep | EvidenceError:
        journal = Journal(repo, "alice")
        digest = "b" * 64 if changed and index else "a" * 64
        barrier.wait(timeout=5)
        try:
            return journal.next_or_replay(run, kind="model", input_fp=digest)
        except EvidenceError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(start, range(2)))
    assert len(rows(repo)) == 1
    if changed:
        assert sum(isinstance(value, EvidenceError) for value in results) == 1
    else:
        assert all(isinstance(value, JournalStep) and value.seq == 1 for value in results)


def test_shared_traversal_assigns_distinct_sequences_under_threads(journal_repo: PostgresRepository) -> None:
    run = new_run(journal_repo)
    journal = Journal(journal_repo, "alice")

    def start(_: int) -> JournalStep:
        return journal.next_or_replay(run, kind="tool", name="memory_search", input_fp="a" * 64)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(start, range(4)))
    assert sorted(value.seq for value in results) == [1, 2, 3, 4]
    assert len(rows(journal_repo)) == 4


def test_unknown_sequence_and_foreign_owner_cannot_invent_completion(journal_repo: PostgresRepository) -> None:
    run = new_run(journal_repo)
    journal = Journal(journal_repo, "alice")
    step = journal.next_or_replay(run, kind="model", input_fp="a" * 64)
    with pytest.raises(EvidenceError, match="尚未开始"):
        journal.complete(replace(step, seq=999), {"text": "不存在"})
    with pytest.raises(ScopeError):
        Journal(journal_repo, "bob").complete(step, {"text": "跨owner"})
    assert rows(journal_repo)[0]["status"] == "started"

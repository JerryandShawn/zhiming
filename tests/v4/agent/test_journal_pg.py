"""Journal identities and completed output are fenced by real PostgreSQL leases."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.agent.journal import Journal, input_fingerprint
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock


def configure_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    def reject_http(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("步骤日志测试禁止外部HTTP请求")

    monkeypatch.setattr(httpx.Client, "send", reject_http)
    for name in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    return p2_repo


@pytest.fixture
def journal_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return configure_repo(p2_repo, monkeypatch)


def new_run(
    repo: PostgresRepository, ident: str = "journal", owner: str = "alice", *, subject: str = "self"
) -> dict[str, Any]:
    run = repo.queue_run(owner, ident, {"message": "合成日志请求"}, subject=subject)
    with repo.transaction(owner) as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id=%s WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
            ("life:" + subject, owner, run["id"]),
        )
    return repo.claim_run(owner, run["id"])


def rows(repo: PostgresRepository, table: str = "core_run_steps") -> list[dict[str, Any]]:
    with repo.transaction("alice") as connection:
        return connection.execute(
            sql.SQL("SELECT * FROM {} ORDER BY run_id,epoch,seq").format(repo.table(table))
        ).fetchall()


def modify_run(repo: PostgresRepository, run: dict[str, Any], clause: str) -> None:
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET {} WHERE owner=%s AND id=%s").format(repo.table("core_runs"), sql.SQL(clause)),
            ("alice", run["id"]),
        )


def test_completed_model_replays_private_normalized_output_after_repository_reopen(
    journal_repo: PostgresRepository,
) -> None:
    repo = journal_repo
    run = new_run(repo)
    journal = Journal(repo, "alice")
    before = repo.get_revision("alice")
    first = journal.next_or_replay(run, kind="model", input_fp=input_fingerprint("model", "", {"messages": []}))
    output = {"text": "合成回答", "reasoning": "合成受控推理", "signature": "合成签名", "tool_calls": []}
    usage = {"input_tokens": None, "output_tokens": 8}
    completed = journal.complete(first, output, usage)
    assert completed.completed and completed.seq == 1 and completed.output == output and completed.usage == usage
    assert "合成受控推理" not in repr(completed) and run["lease_token"] not in repr(completed)
    reopened = PostgresRepository(repo.dsn, schema=repo.schema, initialize=False)
    try:
        replay = Journal(reopened, "alice").next_or_replay(run, kind="model", input_fp=first.input_fp)
        assert replay.completed and replay.output == output and replay.operation_id == first.operation_id
    finally:
        reopened.close()
    assert len(rows(repo)) == 1 and repo.get_revision("alice") == before
    assert repo.fetch_run("alice", run["id"])["calls"] == 0


def test_sequence_is_per_run_and_epoch_and_survives_replay(journal_repo: PostgresRepository) -> None:
    repo = journal_repo
    repo.create_subject("alice", "journal-secondary", "合成独立日志人物")
    first, second = new_run(repo, "first"), new_run(repo, "second", subject="journal-secondary")
    assert first["thread_id"] != second["thread_id"]
    journal = Journal(repo, "alice")
    digest = input_fingerprint("model", "", {})
    step = journal.next_or_replay(first, kind="model", input_fp=digest)
    journal.complete(step, {"text": "合成文本"})
    assert journal.next_or_replay(first, kind="tool", name="time_context", input_fp=digest).seq == 2
    assert journal.next_or_replay(second, kind="model", input_fp=digest).seq == 1
    resumed = Journal(repo, "alice")
    assert resumed.next_or_replay(first, kind="model", input_fp=digest).completed
    pending = resumed.next_or_replay(first, kind="tool", name="time_context", input_fp=digest)
    assert not pending.completed and pending.seq == 2
    assert pending.operation_id == f"run:{first['id']}:e0:s2"


@pytest.mark.parametrize("change", ["kind", "name", "input_fp"])
def test_same_sequence_rejects_changed_identity(journal_repo: PostgresRepository, change: str) -> None:
    run = new_run(journal_repo)
    kwargs = {"kind": "tool", "name": "memory_search", "input_fp": "a" * 64}
    Journal(journal_repo, "alice").next_or_replay(run, **kwargs)
    kwargs[change] = {"kind": "model", "name": "time_context", "input_fp": "b" * 64}[change]
    with pytest.raises(EvidenceError, match="冲突"):
        Journal(journal_repo, "alice").next_or_replay(run, **kwargs)
    assert len(rows(journal_repo)) == 1


@pytest.mark.parametrize("change", ["output", "usage"])
def test_completed_step_is_idempotent_and_cannot_be_overwritten(journal_repo: PostgresRepository, change: str) -> None:
    run = new_run(journal_repo)
    journal = Journal(journal_repo, "alice")
    step = journal.next_or_replay(run, kind="model", input_fp="a" * 64)
    original = journal.complete(step, {"text": "原结果"}, {"input_tokens": 5})
    assert journal.complete(step, {"text": "原结果"}, {"input_tokens": 5}) == original
    values = {"output": {"text": "原结果"}, "usage": {"input_tokens": 5}}
    values[change] = {"output": {"text": "异结果"}, "usage": {"input_tokens": 6}}[change]
    with pytest.raises(EvidenceError, match="覆盖"):
        journal.complete(step, **values)
    assert rows(journal_repo)[0]["output"] == {"text": "原结果"}


@pytest.mark.parametrize(
    "changed", [{"owner": "bob"}, {"subject": "another"}, {"retry_epoch": 1}, {"lease_token": "wrong"}]
)
def test_both_read_and_complete_reject_forged_runtime_identity(
    journal_repo: PostgresRepository, changed: dict[str, Any]
) -> None:
    run = new_run(journal_repo)
    journal = Journal(journal_repo, "alice")
    step = journal.next_or_replay(run, kind="model", input_fp="a" * 64)
    with pytest.raises((ScopeError, LeaseConflict)):
        Journal(journal_repo, "alice").next_or_replay(dict(run, **changed), kind="model", input_fp="a" * 64)
    fields = {"owner": "owner", "subject": "subject", "retry_epoch": "epoch", "lease_token": "lease_token"}
    forged = replace(step, **{fields[key]: value for key, value in changed.items()})
    with pytest.raises((ScopeError, LeaseConflict)):
        journal.complete(forged, {"text": "不得提交"})
    assert rows(journal_repo)[0]["status"] == "started"


@pytest.mark.parametrize(
    "clause",
    [
        "cancel_requested_at=now()",
        "deadline_at=now()-interval '1 second'",
        "status='cancelled'",
        "lease_until=now()-interval '1 second'",
        "lease_token='replaced'",
        "retry_epoch=retry_epoch+1",
    ],
)
def test_late_results_and_reads_use_authoritative_run_state(journal_repo: PostgresRepository, clause: str) -> None:
    run = new_run(journal_repo)
    journal = Journal(journal_repo, "alice")
    step = journal.next_or_replay(run, kind="model", input_fp="a" * 64)
    modify_run(journal_repo, run, clause)
    with pytest.raises(LeaseConflict):
        journal.complete(step, {"text": "迟到结果"})
    with pytest.raises(LeaseConflict):
        Journal(journal_repo, "alice").next_or_replay(run, kind="model", input_fp="a" * 64)
    assert rows(journal_repo)[0]["output"] is None


def test_new_epoch_uses_new_step_without_exposing_previous_epoch(journal_repo: PostgresRepository) -> None:
    run = new_run(journal_repo)
    journal = Journal(journal_repo, "alice")
    step = journal.next_or_replay(run, kind="model", input_fp="a" * 64)
    journal.complete(step, {"text": "旧批次"})
    modify_run(journal_repo, run, "retry_epoch=retry_epoch+1")
    newer = journal_repo.fetch_run("alice", run["id"])
    pending = journal.next_or_replay(newer, kind="model", input_fp="a" * 64)
    assert pending.epoch == 1 and pending.seq == 1 and pending.output is None and not pending.completed
    assert pending.operation_id != step.operation_id and len(rows(journal_repo)) == 2


@pytest.mark.parametrize("invalid", [None, [], {"value": float("nan")}, {"value": ("tuple",)}, {"value": object()}])
def test_non_json_completion_is_rejected_without_echoing_data(journal_repo: PostgresRepository, invalid: Any) -> None:
    run = new_run(journal_repo)
    journal = Journal(journal_repo, "alice")
    step = journal.next_or_replay(run, kind="model", input_fp="a" * 64)
    with pytest.raises(EvidenceError, match="有效JSON对象"):
        journal.complete(step, invalid)
    assert rows(journal_repo)[0]["status"] == "started"


def test_input_fingerprint_is_canonical_and_does_not_coerce_opaque_values() -> None:
    assert input_fingerprint("tool", "memory_write", {"b": 2, "a": 1}) == input_fingerprint(
        "tool", "memory_write", {"a": 1, "b": 2}
    )
    assert input_fingerprint("tool", "memory_write", {}) != input_fingerprint("tool", "memory_forget", {})
    with pytest.raises(EvidenceError):
        input_fingerprint("tool", "memory_write", {"private-key": object()})


def test_boolean_result_is_not_equivalent_to_numeric_receipt(journal_repo: PostgresRepository) -> None:
    run = new_run(journal_repo)
    journal = Journal(journal_repo, "alice")
    step = journal.next_or_replay(run, kind="tool", name="memory_write", input_fp="a" * 64)
    journal.complete(step, {"ok": True, "receipt": [True]})
    with pytest.raises(EvidenceError, match="覆盖"):
        journal.complete(step, {"ok": 1, "receipt": [1]})


def test_clock_is_utc_and_completion_time_cannot_move_backwards(journal_repo: PostgresRepository) -> None:
    run = new_run(journal_repo)
    clock = FrozenClock(datetime.fromisoformat("2026-10-18T23:30:00+08:00"))
    journal = Journal(journal_repo, "alice", clock=clock)
    step = journal.next_or_replay(run, kind="model", input_fp="a" * 64)
    assert step.started_at == datetime(2026, 10, 18, 15, 30, tzinfo=UTC)
    clock.advance(-timedelta(seconds=1))
    with pytest.raises(EvidenceError, match="早于"):
        journal.complete(step, {"text": "合成"})
    clock.advance(timedelta(seconds=2))
    assert journal.complete(step, {"text": "合成"}).finished_at == clock.now()


def test_default_v3_run_does_not_enter_v4_journal(journal_repo: PostgresRepository) -> None:
    run = journal_repo.begin_run("alice", "v3", {"message": "合成旧运行"})
    with pytest.raises(EvidenceError, match="仅用于v4"):
        Journal(journal_repo, "alice").next_or_replay(run, kind="model", input_fp="a" * 64)
    assert rows(journal_repo) == []

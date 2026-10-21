"""Independent real PG listeners observe commit, rollback and scoped event replay."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import psycopg
import pytest
from psycopg import sql

from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository


@pytest.fixture
def event_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("P4 event tests forbid provider HTTP and child processes")

    monkeypatch.setattr(httpx.Client, "send", blocked)
    monkeypatch.setattr(httpx.AsyncClient, "send", blocked)
    monkeypatch.setattr("subprocess.run", blocked)
    for key in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    yield p2_repo


def claimed(repo: PostgresRepository, owner: str = "alice") -> dict[str, Any]:
    source = MemoryService(repo).receive(owner, content="合成流式原话", source_id=uuid.uuid4().hex)
    run = repo.queue_run(owner, uuid.uuid4().hex, {"message": source["content"], "source_message_id": source["id"]})
    with repo.transaction(owner) as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id='life:self' WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            (owner, run["id"]),
        )
    return repo.claim_run(owner, run["id"])


def started(run: dict[str, Any]) -> dict[str, Any]:
    return {"thread_id": "life:self", "message_id": run["request"]["source_message_id"], "incognito": False}


def listener(repo: PostgresRepository) -> psycopg.Connection[Any]:
    connection = psycopg.connect(repo.dsn, autocommit=True)
    connection.execute("LISTEN mj_run")
    return connection


def notified(connection: psycopg.Connection[Any], run: dict[str, Any], *, timeout: float = 0.1) -> list[str]:
    prefix = run["id"] + ":"
    return [notice.payload for notice in connection.notifies(timeout=timeout) if notice.payload.startswith(prefix)]


def stored(repo: PostgresRepository, run: dict[str, Any]) -> list[dict[str, Any]]:
    with repo.transaction(run["owner"]) as connection:
        return connection.execute(
            sql.SQL("SELECT seq,kind,payload FROM {} WHERE owner=%s AND run_id=%s ORDER BY seq").format(
                repo.table("core_run_events")
            ),
            (run["owner"], run["id"]),
        ).fetchall()


def ledger_count(repo: PostgresRepository, owner: str) -> int:
    with repo.transaction(owner) as connection:
        return connection.execute(
            sql.SQL("SELECT count(*) AS n FROM {} WHERE owner=%s AND kind='run_event_v1'").format(
                repo.table("core_operations")
            ),
            (owner,),
        ).fetchone()["n"]


def test_notify_is_delivered_only_after_outer_transaction_commits(event_repo: PostgresRepository) -> None:
    repo, run = event_repo, claimed(event_repo)
    with listener(repo) as observed:
        with repo.transaction(run["owner"]):
            RuntimeEvents(repo, run, None).send("started", started(run))
            assert notified(observed, run, timeout=0.05) == []
            with psycopg.connect(repo.dsn) as independent:
                assert (
                    independent.execute(
                        sql.SQL("SELECT count(*) FROM {} WHERE run_id=%s").format(repo.table("core_run_events")),
                        (run["id"],),
                    ).fetchone()[0]
                    == 0
                )
        assert notified(observed, run) == [run["id"] + ":1"]
    assert stored(repo, run)[0]["kind"] == "started" and ledger_count(repo, "alice") == 1


def test_rollback_removes_event_operation_and_notification(event_repo: PostgresRepository) -> None:
    repo, run = event_repo, claimed(event_repo)
    with listener(repo) as observed:
        with pytest.raises(RuntimeError, match="synthetic rollback"), repo.transaction("alice"):
            RuntimeEvents(repo, run, None).send("started", started(run))
            raise RuntimeError("synthetic rollback")
        assert notified(observed, run) == []
    assert stored(repo, run) == [] and ledger_count(repo, "alice") == 0


def test_started_replay_keeps_original_sequence_timestamp_and_notifies_once(event_repo: PostgresRepository) -> None:
    repo, run, callbacks = event_repo, claimed(event_repo), []
    with listener(repo) as observed:
        RuntimeEvents(repo, run, callbacks.append).send("started", started(run))
        assert notified(observed, run) == [run["id"] + ":1"]
        RuntimeEvents(repo, run, callbacks.append).send("started", started(run))
        assert notified(observed, run) == []
    assert callbacks[0] == callbacks[1] and len(stored(repo, run)) == 1 and ledger_count(repo, "alice") == 1


def test_same_epoch_reclaim_replays_started_but_rejects_previous_lease(event_repo: PostgresRepository) -> None:
    repo, original = event_repo, claimed(event_repo)
    RuntimeEvents(repo, original, None).send("started", started(original))
    before = stored(repo, original)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            ("alice", original["id"]),
        )
    current = repo.claim_run("alice", original["id"])
    assert current["retry_epoch"] == original["retry_epoch"] and current["lease_token"] != original["lease_token"]
    with listener(repo) as observed:
        RuntimeEvents(repo, current, None).send("started", started(current))
        with pytest.raises(CoreError):
            RuntimeEvents(repo, original, None).send("text_delta", {"text": "合成旧租约片"})
        assert notified(observed, current) == []
    assert stored(repo, current) == before and ledger_count(repo, "alice") == 1


def test_explicit_stable_operation_conflict_does_not_append_or_notify(event_repo: PostgresRepository) -> None:
    repo, run = event_repo, claimed(event_repo)
    with listener(repo) as observed:
        RuntimeEvents(repo, run, None).send("text_delta", {"text": "合成原片"}, operation_key="synthetic:fragment:1")
        assert notified(observed, run) == [run["id"] + ":1"]
        with pytest.raises(EvidenceError, match="冲突"):
            RuntimeEvents(repo, run, None).send(
                "text_delta", {"text": "合成异片"}, operation_key="synthetic:fragment:1"
            )
        assert notified(observed, run) == []
    assert len(stored(repo, run)) == 1 and ledger_count(repo, "alice") == 1


def test_plain_repeated_fragments_are_all_preserved_and_notified(event_repo: PostgresRepository) -> None:
    repo, run = event_repo, claimed(event_repo)
    with listener(repo) as observed:
        for _ in range(2):
            RuntimeEvents(repo, run, None).send("text_delta", {"text": "合成重复正文"})
        assert notified(observed, run) == [run["id"] + ":1", run["id"] + ":2"]
    assert [row["payload"]["text"] for row in stored(repo, run)] == ["合成重复正文"] * 2
    assert ledger_count(repo, "alice") == 0


def test_concurrent_stable_append_uses_single_row_operation_and_notify(event_repo: PostgresRepository) -> None:
    repo, run = event_repo, claimed(event_repo)
    with listener(repo) as observed, ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(RuntimeEvents(repo, run, None).send, "started", started(run)) for _ in range(2)]
        for future in futures:
            future.result(timeout=5)
        assert notified(observed, run) == [run["id"] + ":1"]
    assert len(stored(repo, run)) == 1 and ledger_count(repo, "alice") == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner", "bob"),
        ("owner_user_id", "bob"),
        ("subject", "other"),
        ("thread_id", "life:other"),
        ("retry_epoch", 1),
        ("lease_token", "synthetic-wrong-lease"),
    ],
)
def test_forged_scope_cannot_append_or_notify(
    event_repo: PostgresRepository,
    field: str,
    value: Any,
) -> None:
    repo, run = event_repo, claimed(event_repo)
    forged = dict(run, **{field: value})
    with listener(repo) as observed:
        with pytest.raises(CoreError):
            RuntimeEvents(repo, forged, None).send("started", started(run))
        assert notified(observed, run) == []
    assert stored(repo, run) == [] and ledger_count(repo, "alice") == 0


@pytest.mark.parametrize("change", ["cancel", "revoke"])
def test_cancel_or_real_source_invalidation_rejects_old_emitter(
    event_repo: PostgresRepository,
    change: str,
) -> None:
    repo, run = event_repo, claimed(event_repo)
    if change == "revoke":
        repo.invalidate_derived("alice", [], [run["request"]["source_message_id"]])
    else:
        with repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET cancel_requested_at=now() WHERE owner=%s AND id=%s").format(
                    repo.table("core_runs")
                ),
                ("alice", run["id"]),
            )
    with listener(repo) as observed:
        with pytest.raises(CoreError):
            RuntimeEvents(repo, run, None).send("text_delta", {"text": "合成不应发布"})
        assert notified(observed, run) == []
    assert stored(repo, run) == [] and ledger_count(repo, "alice") == 0


@pytest.mark.parametrize("remove", [False, True])
def test_missing_or_privacy_cleared_original_is_never_reconstructed(
    event_repo: PostgresRepository,
    remove: bool,
) -> None:
    repo, run = event_repo, claimed(event_repo)
    RuntimeEvents(repo, run, None).send("started", started(run))
    with repo.transaction("alice") as connection:
        query = (
            "DELETE FROM {} WHERE owner=%s AND run_id=%s"
            if remove
            else "UPDATE {} SET payload='{{}}' WHERE owner=%s AND run_id=%s"
        )
        connection.execute(sql.SQL(query).format(repo.table("core_run_events")), ("alice", run["id"]))
    with listener(repo) as observed:
        with pytest.raises(EvidenceError, match="不能重建"):
            RuntimeEvents(repo, run, None).send("started", started(run))
        assert notified(observed, run) == []
    if remove:
        assert stored(repo, run) == []
    else:
        assert stored(repo, run)[0]["payload"] == {}


def test_terminal_error_replay_emits_one_notification_for_real_failure(event_repo: PostgresRepository) -> None:
    repo, run = event_repo, claimed(event_repo)
    repo.fail_run("alice", run["id"], "合成失败", run["lease_token"])
    with listener(repo) as observed:
        reader = RunEventReader(repo, "alice", run["id"])
        reader.ensure_terminal()
        assert notified(observed, run) == [run["id"] + ":1"]
        reader.ensure_terminal()
        assert notified(observed, run) == []
    assert stored(repo, run)[0]["payload"]["code"] == "RUN_FAILED" and ledger_count(repo, "alice") == 1


def test_completed_operation_does_not_allow_cross_run_replay(event_repo: PostgresRepository) -> None:
    repo, first = event_repo, claimed(event_repo)
    RuntimeEvents(repo, first, None).send("started", started(first))
    repo.fail_run("alice", first["id"], "合成结束", first["lease_token"])
    second = claimed(repo)
    with listener(repo) as observed:
        RuntimeEvents(repo, second, None).send("started", started(second))
        assert notified(observed, second) == [second["id"] + ":1"]
    assert stored(repo, first)[0]["payload"]["message_id"] != stored(repo, second)[0]["payload"]["message_id"]
    assert ledger_count(repo, "alice") == 2

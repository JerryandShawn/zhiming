"""Real PG evidence, rollback and scope boundaries for manual event retention."""

from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.event_retention import EventRetentionSweep
from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories import event_retention_metadata as metadata
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import FrozenClock, set_clock
from tests.v4.streaming_integration.test_event_notify_pg import claimed, started, stored
from tests.v4.streaming_integration.test_event_retention_pg import age_from_baseline, completed
from tests.v4.streaming_integration.test_event_retention_pg import repository_fixture as source_fixture


@pytest.fixture(name="retention_repo")
def repository_fixture(p2_repo, monkeypatch) -> Iterator[PostgresRepository]:
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def failed(repo: PostgresRepository, fragments: int = 2, *, status: str = "failed") -> dict[str, Any]:
    run = claimed(repo)
    events = RuntimeEvents(repo, run, None)
    events.send("started", started(run))
    for _ in range(fragments):
        events.send("text_delta", {"text": "合成私有中间正文"})
    return repo.fail_run("alice", run["id"], "synthetic", run["lease_token"], status=status)


def proofs(repo: PostgresRepository, run: dict[str, Any]) -> list[dict[str, Any]]:
    prefix = metadata.namespace(run)
    with repo.transaction("alice") as connection:
        return connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND kind=%s AND left(operation_id,%s)=%s ORDER BY operation_id"
            ).format(repo.table("core_operations")),
            (run["owner"], metadata.KIND, len(prefix), prefix),
        ).fetchall()


def test_exact_proof_is_body_free_canonical_and_bounded(retention_repo):
    repo = retention_repo
    run = failed(repo, fragments=3)
    age_from_baseline(run, timedelta(hours=24, seconds=1))
    sweep = EventRetentionSweep(repo)
    assert sweep.tick(event_limit=1)["events"] == 1
    assert [row["seq"] for row in stored(repo, run)] == [1, 3, 4]
    evidence = proofs(repo, run)
    assert len(evidence) == 1
    payload = json.loads(evidence[0]["result_id"])
    assert payload.keys() == metadata.TOMBSTONE_KEYS
    assert evidence[0]["fingerprint"] == fingerprint([metadata.KIND, payload])
    assert "text" not in payload and "payload" not in payload and "合成" not in evidence[0]["result_id"]
    assert sweep.tick()["events"] == 2 and sweep.tick()["events"] == 0
    assert len(proofs(repo, run)) == 3


@pytest.mark.parametrize("change", ["kind", "scope", "digest", "seq", "extra", "canonical", "bool"])
def test_tampered_or_foreign_tombstone_cannot_attest_cursor(retention_repo, change):
    repo = retention_repo
    run = failed(repo, fragments=1)
    age_from_baseline(run, timedelta(hours=24, seconds=1))
    EventRetentionSweep(repo).tick()
    proof = proofs(repo, run)[0]
    value, kind = json.loads(proof["result_id"]), proof["kind"]
    if change == "kind":
        kind = "case"
    elif change == "scope":
        value["run_hash"] = "f" * 64
    elif change == "seq":
        value["seq"] += 1
    elif change == "extra":
        value["extra"] = True
    elif change == "bool":
        value["v"] = True
    digest = "0" * 64 if change == "digest" else fingerprint([metadata.KIND, value])
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if change == "canonical":
        raw = " " + raw
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET kind=%s,fingerprint=%s,result_id=%s WHERE owner=%s AND operation_id=%s").format(
                repo.table("core_operations")
            ),
            (kind, digest, raw, "alice", proof["operation_id"]),
        )
    with pytest.raises(EvidenceError, match="事件游标不可用，请重新读取运行状态"):
        RunEventReader(repo, "alice", run["id"]).validate_cursor(2)


def test_failed_cleanup_rolls_back_exact_proof_and_delete(retention_repo, monkeypatch):
    repo = retention_repo
    run = failed(repo, fragments=1)
    age_from_baseline(run, timedelta(hours=24, seconds=1))
    before = stored(repo, run)
    original = metadata.attest_deleted

    def stop_after_attestation(*args, **kwargs):
        original(*args, **kwargs)
        raise EvidenceError("合成清理事务中断")

    monkeypatch.setattr(metadata, "attest_deleted", stop_after_attestation)
    with pytest.raises(EvidenceError, match="合成清理事务中断"):
        EventRetentionSweep(repo).tick()
    assert stored(repo, run) == before and proofs(repo, run) == []


def test_updated_at_is_not_a_commit_anchor(retention_repo):
    repo = retention_repo
    run = completed(repo)
    before = stored(repo, run)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET updated_at=updated_at-interval '31 days' WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            ("alice", run["id"]),
        )
    age_from_baseline(run, timedelta(hours=24) - timedelta(seconds=1))
    assert EventRetentionSweep(repo).tick()["events"] == 0
    assert stored(repo, run) == before


def test_unknown_legacy_anchor_is_skipped_without_inventing_history(retention_repo):
    repo = retention_repo
    run = completed(repo)
    before = stored(repo, run)
    age_from_baseline(run, timedelta(days=31))
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL(
                "UPDATE {} SET usage=usage-%s,updated_at=updated_at-interval '31 days' WHERE owner=%s AND id=%s"
            ).format(repo.table("core_runs")),
            (metadata.KEY, "alice", run["id"]),
        )
    assert EventRetentionSweep(repo).tick()["legacy_skipped"] == 1
    assert stored(repo, run) == before


def test_locked_or_requeued_attempt_is_not_deleted(retention_repo):
    repo = retention_repo
    run = failed(repo)
    age_from_baseline(run, timedelta(days=31))
    before = stored(repo, run)
    with repo.transaction("alice") as connection, ThreadPoolExecutor(max_workers=1) as worker:
        metadata.locked_run(repo, connection, "alice", run["id"])
        assert worker.submit(EventRetentionSweep(repo).tick).result(timeout=2)["events"] == 0
        repo.prepare_retry("alice", run["id"])
    assert EventRetentionSweep(repo).tick()["events"] == 0
    assert stored(repo, run) == before


def test_closed_success_cannot_reopen_events_after_withdrawal(retention_repo):
    repo = retention_repo
    run = completed(repo)
    age_from_baseline(run, timedelta(days=31))
    EventRetentionSweep(repo).tick()
    assert stored(repo, run) == []
    repo.invalidate_derived("alice", [], [run["request"]["source_message_id"]])
    reader = RunEventReader(repo, "alice", run["id"])
    assert reader.page(0) == ([], 0, True)
    reader.ensure_terminal()
    assert stored(repo, run) == []


def test_queued_cancel_gets_real_terminal_anchor(retention_repo):
    repo = retention_repo
    run = failed(repo)
    repo.prepare_retry("alice", run["id"])
    cancelled = DispatcherCancellation(repo).request("alice", run["id"])
    assert metadata.terminal_anchor(cancelled)["status"] == "cancelled"
    age_from_baseline(cancelled, timedelta(days=31))
    EventRetentionSweep(repo).tick()
    assert stored(repo, run) == []
    assert RunEventReader(repo, "alice", run["id"]).page(0) == ([], 0, True)


def test_30_day_cleanup_keeps_other_operation_kinds_and_stable_event_receipts(retention_repo):
    repo = retention_repo
    run = failed(repo, fragments=1)
    age_from_baseline(run, timedelta(hours=24, seconds=1))
    EventRetentionSweep(repo).tick()
    foreign_id = metadata.namespace(run) + "other"
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("INSERT INTO {}(owner,operation_id,fingerprint,kind,result_id) VALUES(%s,%s,%s,%s,%s)").format(
                repo.table("core_operations")
            ),
            ("alice", foreign_id, "0" * 64, "fact", "synthetic-retained-operation"),
        )
    age_from_baseline(run, timedelta(days=31))
    EventRetentionSweep(repo).tick()
    assert proofs(repo, run) == []
    with repo.transaction("alice") as connection:
        rows = connection.execute(
            sql.SQL("SELECT kind FROM {} WHERE owner=%s AND (operation_id=%s OR kind='run_event_v1')").format(
                repo.table("core_operations")
            ),
            ("alice", foreign_id),
        ).fetchall()
    assert {row["kind"] for row in rows} == {"fact", "run_event_v1"}


def test_terminal_with_a_live_lease_is_not_cleaned(retention_repo):
    repo = retention_repo
    run = failed(repo)
    age_from_baseline(run, timedelta(days=31))
    before = stored(repo, run)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET lease_token=%s,lease_until=now()+interval '1 hour' WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            ("synthetic-inconsistent-lease", "alice", run["id"]),
        )
    assert EventRetentionSweep(repo).tick()["events"] == 0
    assert stored(repo, run) == before


def test_construction_does_not_start_a_cleanup_job(retention_repo):
    repo = retention_repo
    run = failed(repo)
    age_from_baseline(run, timedelta(days=31))
    before = stored(repo, run)
    EventRetentionSweep(repo)
    assert stored(repo, run) == before


def test_a_not_yet_due_first_run_cannot_starve_a_due_run(retention_repo, monkeypatch):
    from mingjing_core.repositories import postgres

    identities = iter(["run_z_retention_due", "run_a_retention_later"])
    original = postgres.new_id
    monkeypatch.setattr(postgres, "new_id", lambda prefix: next(identities) if prefix == "run" else original(prefix))
    repo = retention_repo
    due = failed(repo, fragments=1)
    anchor = metadata.instant(metadata.terminal_anchor(due)["at"])
    set_clock(FrozenClock(anchor + timedelta(days=2)))
    later = failed(repo, fragments=1)
    before = stored(repo, later)
    set_clock(FrozenClock(anchor + timedelta(hours=25)))
    assert EventRetentionSweep(repo).tick(limit=1)["events"] == 1
    assert [row["seq"] for row in stored(repo, due)] == [1]
    assert stored(repo, later) == before


@pytest.mark.parametrize("status", ["failed", "stale"])
def test_closed_failure_retry_refuses_without_reopening_or_changing_budget(retention_repo, status):
    repo = retention_repo
    run = failed(repo, status=status)
    age_from_baseline(run, timedelta(days=31))
    EventRetentionSweep(repo).tick()
    before = repo.fetch_run("alice", run["id"])
    assert metadata.is_closed(before) and stored(repo, run) == []
    with pytest.raises(EvidenceError, match="事件历史已过期，请明确发起新请求"):
        repo.prepare_retry("alice", run["id"])
    assert repo.fetch_run("alice", run["id"]) == before
    assert stored(repo, run) == []
    assert RunEventReader(repo, "alice", run["id"]).page(0) == ([], 0, True)

"""Candidate stream writes must not rewind event retention or another usage field."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.event_retention import EventRetentionSweep
from mingjing_core.application.run_event_stream_state import StreamState
from mingjing_core.repositories import event_retention_metadata as retention
from mingjing_core.repositories.postgres import PostgresRepository
from tests.v4.streaming_integration.test_event_notify_pg import stored
from tests.v4.streaming_integration.test_event_retention_pg import age_from_baseline, remove_rows
from tests.v4.streaming_integration.test_event_retention_proofs_pg import failed
from tests.v4.streaming_integration.test_stream_candidate_runtime_pg import ChunkPort, core, submit
from tests.v4.streaming_integration.test_stream_candidate_runtime_pg import stream_repo as source_fixture


@pytest.fixture(name="stream_repo")
def repository_fixture(p2_repo, monkeypatch) -> Iterator[PostgresRepository]:
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def candidate_failure(repo: PostgresRepository) -> dict[str, Any]:
    port = ChunkPort([["合" * 40, SystemExit("synthetic failure after real buffered append")]])
    service = core(repo, port)
    queued = submit(service)
    with pytest.raises(SystemExit, match="synthetic failure after real buffered append"):
        service.execute("alice", queued["id"])
    current = repo.fetch_run("alice", queued["id"])
    assert any(row["kind"] == "text_delta" for row in stored(repo, current))
    assert all(row["kind"] not in {"error", "final"} for row in stored(repo, current))
    return repo.fail_run("alice", current["id"], "synthetic", current["lease_token"])


def test_same_transaction_stream_save_preserves_appended_hwm_and_other_usage(stream_repo, monkeypatch):
    repo, observations = stream_repo, []
    original = StreamState._save

    def observed_save(self, connection, run, metadata):
        if metadata["emitted"]:
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET usage=jsonb_set(usage,'{{synthetic_other}}',%s,true) WHERE owner=%s AND id=%s"
                ).format(repo.table("core_runs")),
                (Jsonb({"counter": 7}), run["owner"], run["id"]),
            )
            before = retention.locked_run(repo, connection, run["owner"], run["id"])
            original(self, connection, run, metadata)
            after = retention.locked_run(repo, connection, run["owner"], run["id"])
            observations.append((before["usage"], after["usage"]))
        else:
            original(self, connection, run, metadata)

    monkeypatch.setattr(StreamState, "_save", observed_save)
    candidate_failure(repo)
    assert observations
    for before, after in observations:
        assert after[retention.KEY] == before[retention.KEY]
        assert after["synthetic_other"] == before["synthetic_other"] == {"counter": 7}


def test_failed_real_candidate_tail_loss_does_not_reuse_sequence(stream_repo):
    repo = stream_repo
    failed_run = candidate_failure(repo)
    rows = stored(repo, failed_run)
    maximum = rows[-1]["seq"]
    remove_rows(repo, failed_run, [row["seq"] for row in rows if row["kind"] == "text_delta"])
    repo.prepare_retry("alice", failed_run["id"])
    retry = repo.claim_run("alice", failed_run["id"])
    RuntimeEvents(repo, retry, None).send("status", {"text": "继续处理中", "phase": "thinking"})
    assert stored(repo, retry)[-1]["seq"] > maximum


@pytest.mark.parametrize("age", [timedelta(hours=25), timedelta(days=31)])
def test_cleanup_persists_actual_maximum_before_any_delete(stream_repo, monkeypatch, age):
    repo = stream_repo
    run = failed(repo, fragments=3)
    maximum = stored(repo, run)[-1]["seq"]
    with repo.transaction("alice") as connection:
        current = retention.locked_run(repo, connection, "alice", run["id"])
        value = retention.state(current)
        value["high_watermark"] = 1
        retention.store(repo, connection, current, value)
    age_from_baseline(run, age)
    observed = []
    original = EventRetentionSweep._rows

    def before_delete(self, connection, current, complete, limit):
        saved = retention.locked_run(repo, connection, "alice", run["id"])
        observed.append(retention.state(saved)["high_watermark"])
        assert observed[-1] >= maximum
        return original(self, connection, current, complete, limit)

    monkeypatch.setattr(EventRetentionSweep, "_rows", before_delete)
    result = EventRetentionSweep(repo).tick()
    assert observed and result["events"] > 0
    assert retention.state(repo.fetch_run("alice", run["id"]))["high_watermark"] >= maximum

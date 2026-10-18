"""Time changes cannot open a second repair round or break its legitimate retry."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from psycopg import sql

from mingjing_core.application.consultation_context import program_clock
from mingjing_core.domain.consultation import ModelUnavailable
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.repositories.runtime_metadata import program_time
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tests import test_core_repair_recovery as recovery


def test_real_transient_repair_retry_preserves_payload_and_identity_after_clock_advances(
    p2_repo: PostgresRepository,
) -> None:
    original = get_clock()
    frozen = FrozenClock(datetime.fromisoformat("2030-01-02T10:30:00+08:00"))
    set_clock(frozen)
    probe = recovery.CoreRepairRecovery("runTest")
    probe.setUp()
    try:
        probe.behavior = ["network", "success"]
        with pytest.raises(ModelUnavailable):
            probe.consult()
        failed = probe.current()
        first_time = probe.service._record("fictional", failed["id"], "program_time")["at"]
        frozen.advance(timedelta(days=1, microseconds=1))
        result = probe.retry(failed)
        current = probe.current()
        assert current["calls"] == 4 and current["repair_used"]
        assert probe.repairs[0] == probe.repairs[1]
        assert len({row["repair_identity"] for row in probe.repair_diagnostics(current)}) == 1
        assert result["validation"]["valid"]
        assert first_time == "2030-01-02T02:30:00+00:00"
        assert probe.service._record("fictional", failed["id"], "program_time")["at"] == first_time
        probe.behavior = ["success"]
        probe.consult("new-business")
        newer = probe.current("new-business")
        assert probe.service._record("fictional", newer["id"], "program_time")["at"] == frozen.now().isoformat()
    finally:
        probe.doCleanups()
        set_clock(original)


def test_stale_retry_epoch_gets_new_program_time_even_with_preserved_intake(p2_repo: PostgresRepository) -> None:
    original = get_clock()
    frozen = FrozenClock(datetime.fromisoformat("2030-01-02T10:30:00+08:00"))
    set_clock(frozen)
    probe = recovery.CoreRepairRecovery("runTest")
    probe.setUp()
    try:
        probe.behavior = ["network"]
        with pytest.raises(ModelUnavailable):
            probe.consult()
        failed = probe.current()
        old_time = probe.service._record("fictional", failed["id"], "program_time")["at"]
        with probe.repo.transaction("fictional") as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET status='stale' WHERE owner='fictional' AND id=%s").format(
                    probe.repo.table("core_runs")
                ),
                (failed["id"],),
            )
        frozen.advance(timedelta(days=1))
        prepared = probe.repo.prepare_retry("fictional", failed["id"])
        assert prepared["run"]["retry_epoch"] == 1
        claimed = probe.repo.claim_run("fictional", failed["id"])
        assert probe.service._record("fictional", failed["id"], "intake") is not None
        assert program_clock(probe.service, "fictional", claimed).now() == frozen.now()
        assert probe.service._record("fictional", failed["id"], "program_time")["at"] != old_time
        assert claimed["calls"] == 3 and claimed["repair_used"]
    finally:
        probe.doCleanups()
        set_clock(original)


def test_program_metadata_is_idempotent_without_semantic_revision_or_call_changes(p2_repo: PostgresRepository) -> None:
    value = p2_repo.begin_run("alice", "metadata", {"message": "合成请求"})
    before = p2_repo.get_revision("alice")
    first = program_time(p2_repo, "alice", value, "2030-01-02T10:30:00+08:00")
    assert first == "2030-01-02T02:30:00+00:00"
    assert program_time(p2_repo, "alice", value, "2030-01-03T02:30:00+00:00") == first
    assert p2_repo.get_revision("alice") == before
    assert p2_repo.fetch_run("alice", value["id"])["calls"] == 0
    assert len(p2_repo.list("alice", "runtime_step")) == 1
    p2_repo.put("alice", "note", "normal", {"content": "合成普通写入"}, expected_revision=0)
    assert p2_repo.get_revision("alice") > before


@pytest.mark.parametrize("invalid", ["lease", "epoch", "time", "owner"])
def test_program_metadata_rejects_invalid_lease_epoch_time_or_owner(p2_repo: PostgresRepository, invalid: str) -> None:
    value = p2_repo.begin_run("alice", "metadata", {"message": "合成请求"})
    program_time(p2_repo, "alice", value, "2030-01-02T02:30:00+00:00")
    changed = dict(value)
    owner, at = "alice", "2030-01-02T02:30:00+00:00"
    if invalid == "lease":
        changed["lease_token"] = "not-the-lease"
    elif invalid == "epoch":
        changed["retry_epoch"] += 1
    elif invalid == "time":
        at = "2030-01-02T02:30:00"
    else:
        owner = "bob"
    before = p2_repo.get_revision("alice")
    with pytest.raises((EvidenceError, LeaseConflict, ScopeError)):
        program_time(p2_repo, owner, changed, at)
    assert p2_repo.get_revision("alice") == before
    assert len(p2_repo.list("alice", "runtime_step")) == 1

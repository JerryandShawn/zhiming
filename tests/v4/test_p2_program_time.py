"""Time changes cannot open a second repair round or break its legitimate retry."""

from datetime import datetime, timedelta

import pytest
from psycopg import sql

from mingjing_core.application.consultation_context import program_clock
from mingjing_core.domain.consultation import ModelUnavailable
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tests import test_core_repair_recovery as recovery


def test_real_transient_repair_retry_preserves_payload_and_identity_after_clock_advances(p2_repo):
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


def test_stale_retry_epoch_gets_new_program_time_even_with_preserved_intake(p2_repo):
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

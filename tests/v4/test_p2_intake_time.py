"""First intake failures preserve time only at an accepted, still-leased boundary."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta

import httpx
import pytest
from psycopg import sql

from mingjing_core.domain.consultation import InvalidAnswer, ModelUnavailable
from mingjing_core.domain.contracts import LeaseConflict
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tests import test_core_repair_recovery as recovery


def intake_probe(behavior: str) -> recovery.CoreRepairRecovery:
    class Probe(recovery.CoreRepairRecovery):
        def respond(self, request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            payload = json.loads(body["messages"][0]["content"][0]["text"])
            if body["tools"][0]["input_schema"].get("title") == "Intake":
                self.intake_payloads.append(deepcopy(payload))
                if len(self.intake_payloads) == 1:
                    self.requests.append("intake-failed")
                    if behavior == "network":
                        raise httpx.ReadTimeout("SYNTHETIC_NETWORK", request=request)
                    if behavior in ("cancel", "expire"):
                        current = self.current()
                        if behavior == "cancel":
                            self.repo.fail_run(
                                "fictional",
                                current["id"],
                                "SYNTHETIC_CANCEL",
                                current["lease_token"],
                                status="cancelled",
                            )
                        else:
                            with self.repo.transaction("fictional") as connection:
                                connection.execute(
                                    sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE id=%s").format(
                                        self.repo.table("core_runs")
                                    ),
                                    (current["id"],),
                                )
                    if behavior in ("503", "cancel", "expire"):
                        return httpx.Response(503, text="SYNTHETIC_FAILURE")
                    content = (
                        []
                        if behavior == "zero_tool"
                        else [{"type": "tool_use", "name": "submit", "input": {"invalid": True}}]
                    )
                    return httpx.Response(200, json={"content": content, "stop_reason": "end_turn"})
            return super().respond(request)

    probe = Probe("runTest")
    probe.intake_payloads = []
    probe.setUp()
    return probe


@pytest.mark.parametrize("behavior", ["network", "503", "zero_tool", "contract"])
def test_accepted_intake_failure_and_clock_advance_reuse_complete_payload(
    p2_repo: PostgresRepository, behavior: str
) -> None:
    original = get_clock()
    frozen = FrozenClock(datetime.fromisoformat("2030-01-02T10:30:00+08:00"))
    set_clock(frozen)
    probe = intake_probe(behavior)
    try:
        with pytest.raises((ModelUnavailable, InvalidAnswer)):
            probe.consult()
        failed = probe.current()
        assert failed["calls"] == 1
        anchor = probe.service._record("fictional", failed["id"], "program_time")
        assert anchor["at"] == frozen.now().isoformat()
        frozen.advance(timedelta(days=1, microseconds=1))
        result = probe.retry(failed)
        current = probe.current()
        assert probe.intake_payloads[0] == probe.intake_payloads[1]
        assert current["retry_epoch"] == 0 and current["calls"] == 4
        assert result["validation"]["valid"]
    finally:
        probe.doCleanups()
        set_clock(original)


@pytest.mark.parametrize("behavior", ["cancel", "expire"])
def test_cancelled_or_expired_first_intake_keeps_charge_but_never_writes_time_step(
    p2_repo: PostgresRepository, behavior: str
) -> None:
    probe = intake_probe(behavior)
    try:
        with pytest.raises(LeaseConflict):
            probe.consult()
        current = probe.current()
        assert current["calls"] == 1
        assert not [row for row in probe.repo.list("fictional", "runtime_step") if row.get("run_id") == current["id"]]
    finally:
        probe.doCleanups()

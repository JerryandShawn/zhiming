"""A repair's late HTTP result cannot overwrite the charged epoch's started row."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_repair_recovery as recovery
from tests.v4.foundation import test_p1_p2_lease as composition

combo_clock = composition.combo_clock
repair_probe = composition.repair_probe


def _late_response(
    probe: recovery.CoreRepairRecovery,
    started: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    quota: bool,
) -> Callable[[httpx.Request], httpx.Response]:
    original = probe.respond

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        payload = json.loads(body["messages"][0]["content"][0]["text"])
        if "errors" in payload:
            current = probe.current()
            started.extend(probe.repair_diagnostics(current))
            steps.extend(probe.repo.list("fictional", "runtime_step"))
            with probe.repo.transaction("fictional") as connection:
                connection.execute(
                    sql.SQL("UPDATE {} SET retry_epoch=retry_epoch+1 WHERE owner=%s AND id=%s").format(
                        probe.repo.table("core_runs")
                    ),
                    ("fictional", current["id"]),
                )
        try:
            return original(request)
        except httpx.ReadTimeout:
            if quota:
                return composition._quota("quota_5h")
            raise

    return respond


@pytest.mark.parametrize("behavior", ["success", "network", "quota_5h"])
def test_repair_late_epoch_result_retains_unknown_started_diagnostic(
    repair_probe: recovery.CoreRepairRecovery, behavior: str
) -> None:
    # Avoid the fixture's quota shortcut: mutate the epoch inside real HTTP
    # handling, then return a parser-backed quota body for that physical call.
    repair_probe.behavior = ["network" if behavior == "quota_5h" else behavior]
    started: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    repair_probe.respond = _late_response(repair_probe, started, steps, behavior == "quota_5h")

    with pytest.raises(InvalidAnswer):
        repair_probe.consult()
    current = repair_probe.current()
    assert len(started) == 1 and started[0]["status"] == "started"
    assert repair_probe.repair_diagnostics(current) == started
    assert repair_probe.repo.list("fictional", "runtime_step") == steps
    assert current["calls"] == len(repair_probe.requests) == 3
    assert current["result"] is None
    assert not repair_probe.service._record("fictional", current["id"], "model:repair")
    with repair_probe.repo.transaction("fictional") as connection:
        charges = connection.execute(
            sql.SQL("SELECT count(*) AS count FROM {} WHERE owner=%s AND run_id=%s").format(
                repair_probe.repo.table("core_model_charges")
            ),
            ("fictional", current["id"]),
        ).fetchone()["count"]
    assert charges == 3

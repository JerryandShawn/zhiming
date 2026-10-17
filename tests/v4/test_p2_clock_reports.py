"""Program time, report periods and policy configuration reach the real boundary."""

import asyncio
from datetime import date, datetime

import pytest

from mingjing_core.adapters.channels.reports import CoreReportAdapter
from mingjing_core.application.consultation import ConsultationService, today
from mingjing_core.application.consultation_context import SYSTEM_POLICY_VERSION
from mingjing_core.domain.report_schedules import report_period, report_period_bounds
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tests.test_core_pg_channels import FixtureModel


@pytest.mark.parametrize(
    "kind,day,start,end,key",
    [
        ("daily", "2026-10-17", "2026-10-17", "2026-10-17", "2026-10-17"),
        ("weekly", "2027-01-01", "2026-12-28", "2027-01-03", "2026-W53"),
        ("monthly", "2028-02-29", "2028-02-01", "2028-02-29", "2028-02"),
        ("quarterly", "2026-10-17", "2026-10-01", "2026-12-31", "2026-Q4"),
    ],
)
def test_report_period_keeps_legacy_key_and_adds_actual_calendar_bounds(kind, day, start, end, key):
    assert report_period(kind, date.fromisoformat(day)) == key
    assert report_period_bounds(kind, date.fromisoformat(day)) == {"start": start, "end": end}


class CapturingModel(FixtureModel):
    def __init__(self):
        super().__init__()
        self.systems = []

    def generate(self, *, system, payload, schema, purpose):
        self.systems.append(system)
        return super().generate(system=system, payload=payload, schema=schema, purpose=purpose)


def test_program_clock_now_history_and_crisis_config_reach_every_real_review_boundary(p2_repo):
    original = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat("2026-10-17T10:30:00+08:00")))
    model = CapturingModel()
    service = ConsultationService(p2_repo, model=model)
    try:
        assert today() == "2026-10-17"
        service.memory.receive(
            "alice", content="合成旧话题", source_id="old", conversation_id="old", at="2026-10-16T09:15:00+08:00"
        )
        result = asyncio.run(
            service.consult(
                owner="alice",
                subject="self",
                message="今天先核实安排",
                request_id="clock",
                conversation_id="new",
                depth="deep",
            )
        )
        assert result["meta"]["system_policy_version"] == SYSTEM_POLICY_VERSION
        assert [row["purpose"] for row in model.requests] == ["intake", "synthesis", "review"]
        for request, system in zip(model.requests, model.systems, strict=True):
            data = request["payload"]["reference_data"]
            assert "2026年10月17日" in data["now"]
            assert any(row["at"] == "2026-10-16 09:15" for row in data["recent_history"])
            assert all(set(row) == {"at", "role", "channel", "content"} for row in data["recent_history"])
            assert all(number in system for number in ("12356", "120", "110"))
    finally:
        service.runtime.purge(result["meta"]["core_run"]["run_id"]) if "result" in locals() else None
        set_clock(original)


@pytest.mark.parametrize(
    "kind,day",
    [("daily", "2026-10-17"), ("weekly", "2026-10-18"), ("monthly", "2026-11-01"), ("quarterly", "2027-01-01")],
)
def test_report_adapter_sends_explicit_date_and_period_into_unchanged_service(p2_repo, kind, day):
    p2_repo.bind_channel("alice", "report", "synthetic-report", binding_kind="task")
    model = FixtureModel()
    service = ConsultationService(p2_repo, model=model)
    result = asyncio.run(
        CoreReportAdapter(".", service=service).prepare(
            external_id="synthetic-report", kind=kind, day=day, depth="fast"
        )
    )
    try:
        run = p2_repo.fetch_run("alice", result["meta"]["core_run"]["run_id"])
        assert run["request"]["selection"]["date"] == day
        assert run["request"]["selection"]["period"] == report_period_bounds(kind, date.fromisoformat(day))
        assert result["report"]["period"] == run["request"]["selection"]["period"]
        assert all(value in run["request"]["message"] for value in result["report"]["period"].values())
    finally:
        service.runtime.purge(result["meta"]["core_run"]["run_id"])

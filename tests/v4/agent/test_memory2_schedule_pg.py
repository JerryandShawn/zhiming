"""Real scheduled archive and idle reflection without live providers or automatic facts."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_background_reflection import IdleMemoryReflection, ScriptedReflectionModel
from mingjing_core.application.memory2_schedule import MemoryMaintenanceSchedule
from mingjing_core.application.threads import ThreadService
from mingjing_core.timekit.clock import FrozenClock

from .test_memory2_archive_pg import event
from .test_memory2_slots_pg import fact
from .test_toolkit_pg import SAID_AT
from tests.test_core_pg_channels import FixtureModel


@pytest.fixture
def scheduled(p2_repo, monkeypatch):
    clock = FrozenClock(SAID_AT)
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", clock)
    return p2_repo, clock


def idle(scheduled):
    repo, clock = scheduled
    thread = ThreadService(repo, clock=clock).create("alice", request_id="life")
    row = fact(repo, "我喜欢合成徒步", "2026-10-17T10:00:00+08:00")
    clock.advance(timedelta(minutes=10))
    return thread, row


def test_registered_schedule_waits_until_owner_0300_then_archives_once(scheduled, monkeypatch):
    repo, _ = scheduled
    _, row, _ = event(repo)
    clock = FrozenClock(datetime.fromisoformat("2026-10-22T02:59:00+08:00"))
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", clock)
    schedule = MemoryMaintenanceSchedule(repo, clock=clock, monotonic=lambda: 1)
    assert schedule.tick()["archived"] == 0
    assert repo.get("alice", "fact", row["id"])["status"] == "active"
    clock.advance(timedelta(minutes=1))
    result = MemoryMaintenanceSchedule(repo, clock=clock).tick()
    assert result["archived"] == 1
    archived = repo.get("alice", "fact", row["id"])
    assert archived["status"] == "archived" and archived["content"] == row["content"]
    before = repo.get_revision("alice")
    assert MemoryMaintenanceSchedule(repo, clock=clock).tick()["archived"] == 0
    assert repo.get_revision("alice") == before


def test_idle_script_produces_pending_proposals_never_profile_or_facts(scheduled):
    repo, clock = scheduled
    thread, row = idle(scheduled)
    service = IdleMemoryReflection(repo, clock)
    assert service.thread("alice", thread["id"], "self") == "completed"
    proposals = repo.list("alice", "proposal")
    assert len(proposals) == 1 and proposals[0]["proposal_type"] == "profile_doc"
    assert proposals[0]["status"] == "pending" and proposals[0]["fact_versions"] == {row["id"]: row["revision"]}
    assert repo.list("alice", "profile_doc") == [] and repo.get("alice", "fact", row["id"]) == row
    before = repo.get_revision("alice")
    assert service.thread("alice", thread["id"], "self") == "unchanged"
    assert repo.get_revision("alice") == before


def test_less_than_ten_minutes_and_incognito_do_not_invoke_script(scheduled):
    repo, clock = scheduled
    thread = ThreadService(repo, clock=clock).create("alice", request_id="life")
    fact(repo, "我喜欢合成徒步", "2026-10-17T10:00:00+08:00")
    private = ThreadService(repo, clock=clock).create("alice", incognito=True, request_id="private")

    class Forbidden:
        def complete(self, snapshot):
            raise AssertionError("ineligible threads cannot reach script")

    service = IdleMemoryReflection(repo, clock, model=Forbidden())
    assert service.thread("alice", thread["id"], "self") == "ineligible"
    clock.advance(timedelta(minutes=10))
    assert service.thread("alice", private["id"], "self") == "ineligible"
    assert repo.list("alice", "proposal") == [] and repo.list("alice", "runtime_step") == []


@pytest.mark.parametrize("mutation", ["none", "touch", "withdraw"])
def test_cross_worker_single_inflight_and_no_long_transaction_then_recheck(scheduled, mutation):
    repo, clock = scheduled
    thread, row = idle(scheduled)
    entered, release = threading.Event(), threading.Event()

    class BlockingScript(ScriptedReflectionModel):
        def complete(self, snapshot):
            assert getattr(repo._local, "connection", None) is None
            entered.set()
            assert release.wait(5)
            return super().complete(snapshot)

    service = IdleMemoryReflection(repo, clock, model=BlockingScript())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.thread, "alice", thread["id"], "self")
        try:
            assert entered.wait(5)
            assert IdleMemoryReflection(repo, clock).thread("alice", thread["id"], "self") == "busy"
            if mutation == "touch":
                clock.advance(timedelta(seconds=1))
                ThreadService(repo, clock=clock).touch("alice", thread["id"])
            elif mutation == "withdraw":
                V4FactMemory(repo).retire_fact("alice", row["id"], expected_revision=row["revision"], scope="source")
        finally:
            release.set()
        assert future.result(timeout=5) == ("completed" if mutation == "none" else "failed")
    assert len(repo.list("alice", "proposal")) == (1 if mutation == "none" else 0)


def test_script_failure_is_safe_and_not_retried_for_same_idle_input(scheduled):
    repo, clock = scheduled
    thread, _ = idle(scheduled)

    class Failing:
        def complete(self, snapshot):
            raise RuntimeError("synthetic-private-error")

    service = IdleMemoryReflection(repo, clock, model=Failing())
    assert service.thread("alice", thread["id"], "self") == "failed"
    assert service.thread("alice", thread["id"], "self") == "unchanged"
    records = repo.list("alice", "runtime_step")
    assert records[0]["code"] == "MEMORY_REFLECTION_FAILED" and "synthetic-private-error" not in str(records)
    assert repo.list("alice", "proposal") == []


def test_real_web_lifespan_registers_scripted_scheduler(scheduled):
    repo, _ = scheduled
    core = ConsultationService(repo, model=FixtureModel())
    app = create_app(core)
    with TestClient(app):
        schedule = app.state.core["memory_maintenance"]
        assert isinstance(schedule, MemoryMaintenanceSchedule)
        assert isinstance(schedule.reflection.model, ScriptedReflectionModel)
        assert not app.state.core["task"].done()


def test_active_native_run_blocks_reflection(scheduled):
    from .test_toolkit_pg import setup

    repo, clock = scheduled
    thread, _ = idle(scheduled)
    harness = setup(repo, "合成正在执行的请求")
    assert IdleMemoryReflection(repo, clock).thread("alice", thread["id"], "self") == "ineligible"
    assert repo.list("alice", "proposal") == []
    harness.finish()

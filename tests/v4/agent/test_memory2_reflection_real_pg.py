"""Real-model idle reflection (plan 50 §3/§6) on real PG with a scripted model; no provider is ever called."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_background_reflection import IdleMemoryReflection
from mingjing_core.application.memory2_reflection_input import DAILY_LIMIT, reflection_mode
from mingjing_core.application.memory2_reflection_model import ScriptedFactModel
from mingjing_core.application.memory2_reflection_real import RealMemoryReflection
from mingjing_core.application.memory2_schedule import MemoryMaintenanceSchedule
from mingjing_core.application.memory2_withdrawals import MemoryWithdrawalService
from mingjing_core.application.threads import ThreadService
from mingjing_core.models.config_policy import ConfigError
from mingjing_core.timekit.clock import FrozenClock

from .test_toolkit_pg import SAID_AT

LIKE = "我喜欢合成徒步"
JOB = "我在合成设计公司做设计师"


@pytest.fixture
def life(p2_repo, monkeypatch):
    clock = FrozenClock(SAID_AT)
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", clock)
    thread = ThreadService(p2_repo, clock=clock).create("alice", request_id="life")
    return p2_repo, clock, thread


def say(repo, clock, text):
    clock.advance(timedelta(seconds=1))
    return V4FactMemory(repo).receive("alice", content=text, source_id=uuid.uuid4().hex, at=clock.now())


def idle(clock):
    clock.advance(timedelta(minutes=10))


def item(message, quote, kind="preference", explicit=True, summary="合成概括"):
    return {"message_id": message["id"], "quote": quote, "kind": kind, "explicit": explicit, "summary": summary}


def reflect(repo, clock, thread, items=(), model=None):
    model = model or ScriptedFactModel(list(items))
    return RealMemoryReflection(repo, clock, model=model).thread("alice", thread["id"], "self"), model


class Forbidden:
    def extract(self, payload):
        raise AssertionError("ineligible input must not reach the model")


def test_switch_defaults_to_scripted_and_rejects_unknown_values(p2_repo):
    assert reflection_mode({}) == "scripted"
    assert reflection_mode({"MEMORY_REFLECTION_MODEL": "real"}) == "real"
    with pytest.raises(ConfigError):
        reflection_mode({"MEMORY_REFLECTION_MODEL": "on"})
    scripted = MemoryMaintenanceSchedule(p2_repo, environment={})
    assert type(scripted.reflection) is IdleMemoryReflection
    real = MemoryMaintenanceSchedule(
        p2_repo, environment={"MEMORY_REFLECTION_MODEL": "real"}, reflection_model=ScriptedFactModel()
    )
    assert type(real.reflection) is RealMemoryReflection


def test_explicit_low_sensitivity_saved_others_pending_with_lineage(life):
    repo, clock, thread = life
    first = say(repo, clock, LIKE + "，周末常去山里。")
    second = say(repo, clock, JOB + "。")
    idle(clock)
    items = [
        item(first, LIKE),
        item(second, JOB, "background"),
        item(first, "周末常去山里", "preference", explicit=False, summary="可能偏好户外"),
        item(second, JOB, "event"),
    ]
    status, _ = reflect(repo, clock, thread, items)
    assert status == "completed"
    facts = {row["content"]: row for row in repo.list("alice", "fact")}
    assert set(facts) == {LIKE, JOB}
    assert all(row["origin"] == "memory2_reflection" and row["auto_written"] for row in facts.values())
    assert facts[LIKE]["source_refs"][0]["message_id"] == first["id"]
    proposals = repo.list("alice", "proposal")
    assert {row["kind"] for row in proposals} == {"preference", "event"}
    inferred = next(row for row in proposals if row["kind"] == "preference")
    assert inferred["status"] == "pending" and inferred["inferred"] is True
    assert inferred["source_ids"] == [first["id"]] and inferred["source_refs"][0]["quote"] == "周末常去山里"
    record = next(row for row in repo.list("alice", "runtime_step") if row.get("task") == "memory2_reflection_real")
    assert record["state"] == "completed" and record["counts"] == {"saved": 2, "pending": 2, "skipped": 0}
    assert LIKE not in str(record) and set(record["source_ids"]) == {first["id"], second["id"]}


def test_input_is_minimal_new_user_text_only(life):
    repo, clock, thread = life
    normal = say(repo, clock, LIKE)
    sensitive = say(repo, clock, "我最近在吃药治疗失眠")
    secret = say(repo, clock, "我的密码是合成口令")
    optout = say(repo, clock, "这句不要记住：我喜欢合成咖啡")
    idle(clock)
    status, model = reflect(repo, clock, thread, [item(normal, LIKE)])
    assert status == "completed"
    sent = {row["id"]: row for row in model.calls[0]["messages"]}
    assert sent[normal["id"]] == {"id": normal["id"], "content": LIKE}
    assert sent[sensitive["id"]] == {"id": sensitive["id"], "needs_ask": True}
    assert secret["id"] not in sent and optout["id"] not in sent
    assert "失眠" not in str(model.calls) and "合成口令" not in str(model.calls)
    later = say(repo, clock, JOB)
    idle(clock)
    status, model = reflect(repo, clock, thread)
    assert status == "completed" and [row["id"] for row in model.calls[0]["messages"]] == [later["id"]]


def test_withdrawn_original_is_never_sent_or_used(life):
    repo, clock, thread = life
    kept = say(repo, clock, LIKE)
    gone = say(repo, clock, JOB)
    memory = V4FactMemory(repo)
    command = say(repo, clock, "删除这条来源消息")
    MemoryWithdrawalService(memory).delete_source(
        "alice",
        "self",
        gone["id"],
        expected_revision=gone["revision"],
        message_id=command["id"],
        operation_id="pre-reflection-delete",
    )
    idle(clock)
    status, model = reflect(repo, clock, thread, [item(kept, LIKE)])
    assert status == "completed"
    assert gone["id"] not in str(model.calls) and JOB not in str(model.calls)


def test_deleting_original_removes_derived_memory_into_privacy_ledger(life):
    repo, clock, thread = life
    source = say(repo, clock, LIKE + "，周末常去山里。")
    idle(clock)
    items = [item(source, LIKE), item(source, "周末常去山里", explicit=False)]
    assert reflect(repo, clock, thread, items)[0] == "completed"
    fact = repo.list("alice", "fact")[0]
    proposal = repo.list("alice", "proposal")[0]
    command = say(repo, clock, "删除这条来源消息")
    MemoryWithdrawalService(V4FactMemory(repo)).delete_source(
        "alice",
        "self",
        source["id"],
        expected_revision=source["revision"],
        message_id=command["id"],
        operation_id="delete-reflected-original",
    )
    assert repo.get("alice", "fact", fact["id"], include_deleted=True)["status"] == "deleted"
    assert repo.is_revoked("alice", "fact", fact["id"]) and repo.is_revoked("alice", "message", source["id"])
    assert repo.get("alice", "proposal", proposal["id"], include_deleted=True)["status"] == "deleted"
    # The run record is outside the existing closure kinds; it holds only opaque ids and counts, never text.
    record = next(row for row in repo.list("alice", "runtime_step") if row.get("task") == "memory2_reflection_real")
    assert record["fact_ids"] == [fact["id"]] and record["proposal_ids"] == [proposal["id"]]
    assert LIKE not in str(repo.list("alice", "runtime_step"))
    assert repo.list("alice", "fact") == [] and LIKE not in str(repo.list("alice", "proposal"))


def test_user_can_withdraw_an_auto_written_fact(life):
    repo, clock, thread = life
    source = say(repo, clock, LIKE)
    idle(clock)
    assert reflect(repo, clock, thread, [item(source, LIKE)])[0] == "completed"
    fact = repo.list("alice", "fact")[0]
    command = say(repo, clock, "撤销这条记忆")
    MemoryWithdrawalService(V4FactMemory(repo)).withdraw_fact(
        "alice",
        "self",
        fact["id"],
        expected_revision=fact["revision"],
        message_id=command["id"],
        operation_id="undo-auto-fact",
    )
    assert repo.is_revoked("alice", "fact", fact["id"])
    clock.advance(timedelta(minutes=10))
    assert reflect(repo, clock, thread, [], model=ScriptedFactModel())[0] == "completed"
    assert repo.list("alice", "fact") == []


def test_ineligible_threads_and_memory_off_never_call_model(life):
    repo, clock, thread = life
    say(repo, clock, LIKE)
    assert reflect(repo, clock, thread, model=Forbidden())[0] == "ineligible"
    private = ThreadService(repo, clock=clock).create("alice", incognito=True, request_id="private")
    idle(clock)
    service = RealMemoryReflection(repo, clock, model=Forbidden())
    assert service.thread("alice", private["id"], "self") == "ineligible"
    settings = repo.assert_scope("alice", "self")
    V4FactMemory(repo).update_settings(
        "alice", {**settings["settings"], "auto_save_low_sensitivity": False}, expected_revision=settings["revision"]
    )
    assert service.thread("alice", thread["id"], "self") == "memory_off"
    assert [row for row in repo.list("alice", "runtime_step")] == []


def test_daily_budget_counts_attempts_and_resets_next_owner_day(life):
    repo, clock, thread = life
    for _ in range(DAILY_LIMIT):
        say(repo, clock, LIKE + uuid.uuid4().hex[:4])
        idle(clock)
        assert reflect(repo, clock, thread)[0] == "completed"
    say(repo, clock, JOB)
    idle(clock)
    assert reflect(repo, clock, thread, model=Forbidden())[0] == "budget_exhausted"
    clock.advance(timedelta(days=1))
    assert reflect(repo, clock, thread)[0] == "completed"


def test_failure_is_recorded_without_private_text_and_not_retried(life):
    repo, clock, thread = life
    source = say(repo, clock, LIKE)
    idle(clock)

    class Failing:
        calls = 0

        def extract(self, payload):
            Failing.calls += 1
            raise RuntimeError("synthetic-private-error " + LIKE)

    assert reflect(repo, clock, thread, model=Failing())[0] == "failed"
    assert reflect(repo, clock, thread, model=Failing())[0] == "unchanged" and Failing.calls == 1
    record = next(row for row in repo.list("alice", "runtime_step") if row.get("task") == "memory2_reflection_real")
    assert record["state"] == "failed" and "synthetic-private-error" not in str(record) and LIKE not in str(record)
    assert repo.list("alice", "fact") == [] and repo.list("alice", "proposal") == []
    bad = ScriptedFactModel([item(source, "不在原话里的内容")])
    say(repo, clock, JOB)
    idle(clock)
    assert reflect(repo, clock, thread, model=bad)[0] == "completed"
    assert repo.list("alice", "fact") == []


def test_one_inflight_per_thread_and_new_activity_supersedes(life):
    repo, clock, thread = life
    source = say(repo, clock, LIKE)
    idle(clock)
    entered, release = threading.Event(), threading.Event()

    class Blocking(ScriptedFactModel):
        def extract(self, payload):
            assert getattr(repo._local, "connection", None) is None
            entered.set()
            assert release.wait(5)
            return super().extract(payload)

    service = RealMemoryReflection(repo, clock, model=Blocking([item(source, LIKE)]))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.thread, "alice", thread["id"], "self")
        try:
            assert entered.wait(5)
            assert reflect(repo, clock, thread, model=Forbidden())[0] == "busy"
            clock.advance(timedelta(seconds=1))
            ThreadService(repo, clock=clock).touch("alice", thread["id"])
        finally:
            release.set()
        assert future.result(timeout=5) == "superseded"
    assert repo.list("alice", "fact") == []
    idle(clock)
    assert reflect(repo, clock, thread, [item(source, LIKE)])[0] == "completed"
    assert [row["content"] for row in repo.list("alice", "fact")] == [LIKE]

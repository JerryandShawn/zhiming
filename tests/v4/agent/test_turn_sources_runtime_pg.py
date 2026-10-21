"""Merged and in-flight messages remain distinct originals through real tool writes."""

import uuid

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.thread_inbox import ThreadInbox
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.models.port import ToolCall

from .test_agent_runtime_pg import repository_fixture
from .test_loop_cycle_support import ScriptedPort, answer, modify
from .test_private_runtime_pg import execute


@pytest.fixture(name="turn_repo")
def repository(p2_repo, monkeypatch):
    yield from repository_fixture.__wrapped__(p2_repo, monkeypatch)


def intake(repo):
    with repo.transaction("alice") as connection:
        settings = dict(repo.assert_scope("alice")["settings"], runtime="v4")
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id='alice'").format(repo.table("core_owners")), (Jsonb(settings),)
        )
    thread = ThreadService(repo).create("alice", request_id="merged-runtime")
    return ThreadIngress(ConsultationService(repo)), thread["id"]


def writer(source):
    return dict(message_id=source["id"], quote=source["content"], summary=source["content"], kind="preference")


def test_two_merged_originals_are_both_visible_and_independently_writable(turn_repo):
    repo = turn_repo
    ingress, thread = intake(repo)
    sources = [
        ingress.receive(owner="alice", thread_id=thread, message=text, request_id=uuid.uuid4().hex)
        for text in ("我喜欢合成蓝杯", "我喜欢合成绿笔")
    ]
    queued = ingress.queue(
        owner="alice", thread_id=thread, source_ids=[row["id"] for row in sources], request_id="batch"
    )
    run = repo.claim_run("alice", queued["id"], lease_seconds=150)
    port = ScriptedPort(
        [
            answer(
                "",
                [
                    ToolCall("first", "memory_write", writer(sources[0])),
                    ToolCall("second", "memory_write", writer(sources[1])),
                ],
            ),
            answer("已记住这两个偏好〔f1〕〔f2〕"),
        ]
    )
    result, _ = execute(repo, run, port)
    assert len(repo.list("alice", "fact")) == 2
    request = port.requests[0]["messages"]
    assert all(
        sum(message.role == "user" and message.content == source["content"] for message in request) == 1
        for source in sources
    )
    assert all(source["id"] in str(request) for source in sources)
    reply = repo.get("alice", "message", result["message_id"])
    assert set(row["id"] for row in sources).issubset(reply["source_ids"])


def test_inflight_supplement_is_adopted_before_next_model_and_not_answered_twice(turn_repo):
    repo = turn_repo
    ingress, thread = intake(repo)
    queued = ingress.submit(owner="alice", thread_id=thread, message="合成第一问", request_id="parent")
    run = repo.claim_run("alice", queued["id"], lease_seconds=150)
    child = []

    class SupplementPort(ScriptedPort):
        def stream(self, messages, **kwargs):
            if not self.requests:
                fallback = ingress.submit(owner="alice", thread_id=thread, message="我喜欢合成紫壶", request_id="child")
                child.append(fallback)
                source = repo.get("alice", "message", fallback["request"]["source_message_id"])
                self.responses[1] = answer("", [ToolCall("save-supplement", "memory_write", writer(source))])
            yield from super().stream(messages, **kwargs)

    port = SupplementPort(
        [answer("", [ToolCall("clock", "time_context", {})]), answer("placeholder"), answer("已记住这个偏好〔f1〕")]
    )
    result, _ = execute(repo, run, port)
    assert len(port.requests) == 3 and len(repo.list("alice", "fact")) == 1
    assert child[0]["request"]["source_message_id"] in repo.get("alice", "message", result["message_id"])["source_ids"]
    assert ThreadInbox(repo).recover("alice")["consumed"] == 1
    assert repo.fetch_run("alice", child[0]["id"])["status"] == "cancelled"
    assert ThreadInbox(repo).recover("alice") == {"queued": 0, "consumed": 0, "revoked": 0}


def test_adopted_supplement_replays_after_completed_model_without_losing_lineage(turn_repo, monkeypatch):
    repo = turn_repo
    ingress, thread = intake(repo)
    queued = ingress.submit(owner="alice", thread_id=thread, message="合成重放第一问", request_id="replay-parent")
    run = repo.claim_run("alice", queued["id"], lease_seconds=150)
    child = []

    class SupplementPort(ScriptedPort):
        def stream(self, messages, **kwargs):
            if not self.requests:
                child.append(
                    ingress.submit(owner="alice", thread_id=thread, message="合成补充偏好", request_id="replay-child")
                )
            yield from super().stream(messages, **kwargs)

    def crash(*args, **kwargs):
        raise SystemExit("synthetic crash before final commit")

    original = AgentFinalizer.finalize
    monkeypatch.setattr(AgentFinalizer, "finalize", crash)
    port = SupplementPort([answer("", [ToolCall("replay-clock", "time_context", {})]), answer("合成回复")])
    with pytest.raises(SystemExit):
        execute(repo, run, port)
    monkeypatch.setattr(AgentFinalizer, "finalize", original)
    modify(repo, run, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", run["id"], lease_seconds=150)
    replay = ScriptedPort([])
    result, _ = execute(repo, reclaimed, replay)
    assert replay.requests == []
    reply = repo.get("alice", "message", result["message_id"])
    assert child[0]["request"]["source_message_id"] in reply["source_ids"]
    assert ThreadInbox(repo).recover("alice")["consumed"] == 1

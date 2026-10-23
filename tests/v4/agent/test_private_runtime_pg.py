"""Private Runtime traverses real storage without leaking into life contexts."""

import json
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from psycopg import sql

from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.incognito_reminders import CONFIRM_QUESTION
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.private_retention import retire_private_thread
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.history import history_window
from mingjing_core.models.port import ToolCall

from .test_agent_runtime_pg import queued
from .test_agent_runtime_pg import repository_fixture as source_fixture
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, modify


@pytest.fixture(name="private_runtime_repo")
def repository(p2_repo, monkeypatch):
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def private_run(repo, thread, text):
    source = ThreadService(repo).receive("alice", thread["id"], text, request_id=uuid.uuid4().hex)
    request = dict(message=text, source_message_id=source["id"], case_ids=[], incognito=True, thread_id=thread["id"])
    run = repo.queue_run("alice", uuid.uuid4().hex, request)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id=%s WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
            (thread["id"], "alice", run["id"]),
        )
    return repo.claim_run("alice", run["id"], lease_seconds=150)


def execute(repo, run, port):
    events = []
    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"], events.append
    )
    return result, events


def test_private_reply_is_thread_bound_replayable_and_scrubbed(private_runtime_repo):
    repo = private_runtime_repo
    thread = ThreadService(repo).create("alice", incognito=True, request_id="private-runtime")
    run = private_run(repo, thread, "这是合成私密暗语青橙沙")
    port = ScriptedPort([answer("我听到了合成私密暗语")])
    result, events = execute(repo, run, port)
    assert result["schema"] == "core4.0"
    assert events[0]["data"]["incognito"] is True
    assert events[0]["data"]["thread_id"] == thread["id"]
    message = repo.get("alice", "message", result["message_id"])
    assert message["incognito"] and message["search_tokens"] == ""
    assert message["thread_id"] == thread["id"]
    assert repo.list("alice", "fact") == []
    assert history_window(repo, "alice", "self", "shared", 50, None, "") == []
    assert execute(repo, run, ScriptedPort([]))[0] == result
    retire_private_thread(repo, "alice", thread["id"], expired_only=False)
    assert repo.fetch_run("alice", run["id"])["request"] == {}
    assert repo.fetch_run("alice", run["id"])["result"] is None
    with repo.transaction("alice") as connection:
        rows = connection.execute(
            sql.SQL("SELECT data FROM {} WHERE owner=%s AND kind='runtime_step'").format(repo.table("core_entities")),
            ("alice",),
        ).fetchall()
    assert "青橙沙" not in json.dumps(rows, ensure_ascii=False)


def test_two_private_threads_and_life_never_share_context(private_runtime_repo):
    repo = private_runtime_repo
    first = ThreadService(repo).create("alice", incognito=True, request_id="first")
    run = private_run(repo, first, "合成甲线程独有暗号青橙沙")
    execute(repo, run, ScriptedPort([answer("合成甲回复")]))
    second = ThreadService(repo).create("alice", incognito=True, request_id="second")
    run2 = private_run(repo, second, "合成乙线程")
    port = ScriptedPort([answer("合成乙回复")])
    execute(repo, run2, port)
    assert "青橙沙" not in str(port.requests)
    life = queued(repo, "合成人生线程")
    life_port = ScriptedPort([answer("合成普通回复")])
    execute(repo, life, life_port)
    assert "青橙沙" not in str(life_port.requests)


def test_mismatched_private_flag_is_rejected_before_model(private_runtime_repo):
    repo = private_runtime_repo
    run = queued(repo)
    modify(repo, run, "thread_id='incognito:forged'")
    with pytest.raises(EvidenceError, match="无痕"):
        execute(repo, run, ScriptedPort([]))


@pytest.mark.parametrize("private", [False, True])
def test_authorized_queued_boundary_excludes_later_user_messages(private_runtime_repo, private):
    repo = private_runtime_repo
    if private:
        thread = ThreadService(repo).create("alice", incognito=True, request_id="boundary")
        run = private_run(repo, thread, "合成较早轮次")
        ThreadService(repo).receive("alice", thread["id"], "未来消息独有暗号浅棕石", request_id="later")
    else:
        run = queued(repo, "合成较早轮次")
        MemoryService(repo).receive("alice", content="未来消息独有暗号浅棕石", source_id="later")
    port = ScriptedPort([answer("合成较早回复")])
    result, _ = execute(repo, run, port)
    assert result["schema"] == "core4.0"
    assert "浅棕石" not in str(port.requests)


@pytest.mark.parametrize("approval,expected", [("可以", "saved"), ("不保存", "rejected")])
def test_private_reminder_journals_one_real_ask_and_requires_new_user_answer(private_runtime_repo, approval, expected):
    repo = private_runtime_repo
    thread = ThreadService(repo).create("alice", incognito=True, request_id="private-reminder")
    text = "请在2026-10-19 10:30提醒我喝水"
    run = private_run(repo, thread, text)
    args = dict(
        text="喝水", due_at="2026-10-19T10:30:00+08:00", message_id=run["request"]["source_message_id"], quote=text
    )
    port = ScriptedPort([answer("", [ToolCall("reminder-one", "set_reminder", args)])])
    result, events = execute(repo, run, port)
    assert result["asked"] is not None, [m.content for m in port.requests[-1]["messages"] if m.role == "tool"]
    assert result["asked"]["question"] == CONFIRM_QUESTION
    assert sum(row["type"] == "ask_user" for row in events) == 1
    assert len(port.requests) == 1
    assert repo.list("alice", "reminder") == []
    with repo.transaction("alice") as connection:
        steps = connection.execute(
            sql.SQL("SELECT name FROM {} WHERE owner=%s AND run_id=%s AND kind='tool' ORDER BY seq").format(
                repo.table("core_run_steps")
            ),
            ("alice", run["id"]),
        ).fetchall()
    assert [row["name"] for row in steps] == ["set_reminder", "ask_user"]
    assert execute(repo, run, ScriptedPort([]))[0] == result
    next_run = private_run(repo, thread, approval)
    execute(repo, next_run, ScriptedPort([answer("已处理这条提醒的单独确认")]))
    state = repo.fetch_run("alice", next_run["id"])["usage"]["agent_runtime"]
    assert state["private_reminder_status"] == expected
    saved = repo.list("alice", "reminder")
    assert len(saved) == int(expected == "saved")
    if saved:
        assert saved[0]["source"] == "incognito_explicit"
        assert not any(key in saved[0] for key in ("source_ids", "thread_id", "run_id"))
    assert repo.list("alice", "fact") == []


def test_native_source_preserves_timestamp_and_cannot_move_existing_life_message(private_runtime_repo):
    repo = private_runtime_repo
    service = ThreadService(repo)
    life = service.create("alice", request_id="life-native")
    at = datetime.fromisoformat("2026-10-17T09:00:00+08:00")
    source = service.receive("alice", life["id"], "合成来源", request_id="native", source_id="native-id", at=at)
    assert source["at"] == at.isoformat()
    private = service.create("alice", incognito=True, request_id="private-native")
    with pytest.raises(ScopeError):
        service.receive("alice", private["id"], "合成来源", request_id="other", source_id="native-id", at=at)
    with pytest.raises(EvidenceError, match="时区"):
        service.receive("alice", private["id"], "合成", request_id="naive", at=at.replace(tzinfo=None))


def test_private_confirmation_survives_crash_without_resaving_or_changing_prompt(private_runtime_repo, monkeypatch):
    repo = private_runtime_repo
    thread = ThreadService(repo).create("alice", incognito=True, request_id="resume-reminder")
    run = private_run(repo, thread, "请在2026-10-19 10:30提醒我喝水")
    args = dict(
        text="喝水",
        due_at="2026-10-19T10:30:00+08:00",
        message_id=run["request"]["source_message_id"],
        quote=run["request"]["message"],
    )
    execute(repo, run, ScriptedPort([answer("", [ToolCall("reminder", "set_reminder", args)])]))
    approved = private_run(repo, thread, "可以")
    original = AgentFinalizer.finalize

    def crash(*args, **kwargs):
        raise SystemExit("synthetic crash after explicit approval")

    monkeypatch.setattr(AgentFinalizer, "finalize", crash)
    with pytest.raises(SystemExit):
        execute(repo, approved, ScriptedPort([answer("已处理提醒确认")]))
    first = repo.fetch_run("alice", approved["id"])["usage"]["agent_runtime"]["rendered_system_sha256"]
    monkeypatch.setattr(AgentFinalizer, "finalize", original)
    modify(repo, approved, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", approved["id"], lease_seconds=150)
    port = ScriptedPort([])
    execute(repo, reclaimed, port)
    assert port.requests == [] and len(repo.list("alice", "reminder")) == 1
    assert repo.fetch_run("alice", approved["id"])["usage"]["agent_runtime"]["rendered_system_sha256"] == first

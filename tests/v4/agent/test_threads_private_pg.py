"""Private thread bodies never enter public history, FTS or persistent authority."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.private_retention import retire_private_thread
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.history import history_window
from mingjing_core.memory.tokenize import tokenize
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock


@pytest.fixture
def threads(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> ThreadService:
    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("线程测试禁止外部HTTP")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    return ThreadService(p2_repo, clock=FrozenClock(datetime.fromisoformat("2026-10-17T16:30:00+08:00")))


def create_private(threads: ThreadService) -> tuple[dict, dict]:
    thread = threads.create("alice", incognito=True, request_id="private-synthetic")
    message = threads.receive("alice", thread["id"], "请保存我喜欢合成私密暗语紫云石", request_id="private-message")
    return thread, message


def test_life_and_private_sources_are_idempotent_and_have_separate_identity(threads: ThreadService) -> None:
    life = threads.create("alice", request_id="life-synthetic")
    private = threads.create("alice", incognito=True, request_id="private-synthetic")
    assert threads.create("alice", incognito=True, request_id="private-synthetic")["id"] == private["id"]
    source = threads.receive("alice", life["id"], "合成普通原话", request_id="same-authenticated-source")
    hidden = threads.receive("alice", private["id"], "合成私密原话", request_id="same-authenticated-source")
    replay = threads.receive("alice", private["id"], "合成私密原话", request_id="same-authenticated-source")
    assert source["id"] != hidden["id"] and hidden["id"] == replay["id"]
    assert threads.memory.get_source("alice", source["id"])["thread_id"] == "life:self"
    assert threads.history("alice", private["id"])[0]["content"] == "合成私密原话"
    with pytest.raises(EvidenceError):
        threads.receive("alice", private["id"], "修改旧原话", request_id="same-authenticated-source")


def test_private_source_is_absent_from_history_search_and_long_term_writes(threads: ThreadService) -> None:
    thread, message = create_private(threads)
    assert message["incognito"] and message["search_tokens"] == ""
    assert threads.memory.sources("alice") == []
    assert threads.memory.snapshot("alice")["history"] == []
    assert threads.memory.current_source_context("alice", "self", message["id"], [{"quote": message["content"]}]) == {
        "facts": [],
        "versions": {},
    }
    assert history_window(threads.repo, "alice", "self", "shared", 50, None, "") == []
    assert threads.repo.search("alice", "self", tokenize("紫云石"), ["message"]) == []
    assert threads.history("alice", thread["id"])[0]["id"] == message["id"]
    for write in (
        lambda: threads.memory.save_fact("alice", "self", message["id"], message["content"]),
        lambda: threads.memory.grant_authorization("alice", "self", message["id"], message["content"]),
        lambda: threads.memory.create_case("alice", "self", "合成事项", message_id=message["id"]),
    ):
        with pytest.raises(EvidenceError, match="无痕"):
            write()
    assert threads.repo.list("alice", "fact") == threads.repo.list("alice", "consent") == []


def test_owner_subject_thread_and_expiry_are_enforced(threads: ThreadService) -> None:
    thread, _ = create_private(threads)
    with pytest.raises(ScopeError):
        threads.get("bob", thread["id"])
    with pytest.raises(ScopeError):
        threads.get("alice", thread["id"], subject="unconsented")
    threads.clock.advance(timedelta(hours=23, minutes=59))
    threads.touch("alice", thread["id"])
    threads.clock.advance(timedelta(minutes=2))
    assert threads.get("alice", thread["id"])
    threads.clock.advance(timedelta(hours=24))
    with pytest.raises(EvidenceError, match="到期"):
        threads.get("alice", thread["id"])


def seed_private_run(threads: ThreadService, thread: dict, source: dict) -> dict:
    run = threads.repo.queue_run(
        "alice", "private-run", {"message": source["content"], "source_message_id": source["id"]}
    )
    with threads.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id=%s WHERE id=%s").format(threads.repo.table("core_runs")),
            (thread["id"], run["id"]),
        )
    run = threads.repo.claim_run("alice", run["id"])
    with threads.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET result=%s,checkpoint=%s WHERE id=%s").format(threads.repo.table("core_runs")),
            (Jsonb({"text": "private body"}), Jsonb({"body": "private body"}), run["id"]),
        )
        connection.execute(
            sql.SQL("INSERT INTO {}(owner,run_id,seq,kind,payload) VALUES(%s,%s,1,'text_delta',%s)").format(
                threads.repo.table("core_run_events")
            ),
            ("alice", run["id"], Jsonb({"text": "private body"})),
        )
        connection.execute(
            sql.SQL(
                "INSERT INTO {}(owner,run_id,epoch,seq,kind,name,status,input_fp,output) "
                "VALUES(%s,%s,0,1,'model','primary','completed','synthetic',%s)"
            ).format(threads.repo.table("core_run_steps")),
            ("alice", run["id"], Jsonb({"reasoning": "private body"})),
        )
    return run


def test_expiry_scrubs_every_private_run_body_and_preserves_life_and_other_owner(threads: ThreadService) -> None:
    thread, source = create_private(threads)
    life = threads.create("alice", request_id="life-synthetic")
    normal = threads.receive("alice", life["id"], "保留的合成原话", request_id="life-message")
    run = seed_private_run(threads, thread, source)
    reply = threads.record_private_reply("alice", run, "私密合成回答")
    assert [row["content"] for row in history_window(threads.repo, "alice", "self", "shared", 50, None, "")] == [
        "保留的合成原话"
    ]
    other = threads.create("bob", incognito=True, request_id="other-synthetic")
    assert not retire_private_thread(threads.repo, "alice", thread["id"], clock=threads.clock)["retired"]
    threads.clock.advance(timedelta(hours=25))
    assert retire_private_thread(threads.repo, "alice", thread["id"], clock=threads.clock)["messages"] == 2
    stored = threads.repo.fetch_run("alice", run["id"])
    assert (
        stored["request"] == stored["checkpoint"] == {} and stored["result"] is None and stored["lease_token"] is None
    )
    assert stored["status"] == "revoked" and threads.memory.get_source("alice", reply["id"])["content"] == ""
    assert threads.memory.get_source("alice", normal["id"])["content"] == "保留的合成原话"
    assert threads.repo.get("bob", "thread", other["id"])["status"] == "active"
    with threads.repo.transaction("alice") as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT payload FROM {} WHERE run_id=%s").format(threads.repo.table("core_run_events")),
                (run["id"],),
            ).fetchone()["payload"]
            == {}
        )
        assert (
            connection.execute(
                sql.SQL("SELECT output FROM {} WHERE run_id=%s").format(threads.repo.table("core_run_steps")),
                (run["id"],),
            ).fetchone()["output"]
            is None
        )
    assert not retire_private_thread(threads.repo, "alice", thread["id"], clock=threads.clock)["retired"]
    with pytest.raises(EvidenceError):
        threads.create("alice", incognito=True, request_id="private-synthetic")

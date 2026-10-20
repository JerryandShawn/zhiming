"""Thread intake and dormant fallback use real PG, with no model or external delivery."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.thread_inbox import ThreadInbox
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="inbox_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def set_runtime(repo: PostgresRepository, runtime: Any) -> None:
    with repo.transaction("alice") as connection:
        settings = dict(repo.assert_scope("alice")["settings"], runtime=runtime)
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id='alice'").format(repo.table("core_owners")), (Jsonb(settings),)
        )


def ingress(repo: PostgresRepository, *, owner: str = "alice", private: bool = False) -> tuple[ThreadIngress, str]:
    thread = ThreadService(repo).create(owner, incognito=private, request_id=uuid.uuid4().hex)
    return ThreadIngress(ConsultationService(repo)), thread["id"]


def submit(service: ThreadIngress, thread: str, text: str = "合成问题", **kwargs: Any) -> dict[str, Any]:
    return service.submit(owner="alice", thread_id=thread, message=text, request_id=uuid.uuid4().hex, **kwargs)


def test_default_v3_and_owner_v4_are_persisted_without_execution(inbox_repo: PostgresRepository) -> None:
    service, thread = ingress(inbox_repo)
    first = submit(service, thread)
    assert (first["runtime"], first["status"], first["calls"], first["thread_id"], first["lane"]) == (
        "v3",
        "queued",
        0,
        thread,
        "interactive",
    )
    set_runtime(inbox_repo, "v4")
    second = submit(service, thread, "合成第二问")
    assert second["runtime"] == "v4" and second["calls"] == 0
    assert inbox_repo.fetch_run("alice", first["id"])["runtime"] == "v3"


def test_duplicate_operation_retains_original_runtime_and_one_source(inbox_repo: PostgresRepository) -> None:
    service, thread = ingress(inbox_repo)
    request = dict(owner="alice", thread_id=thread, message="  合成原话\n ", request_id="stable-message")
    first = service.submit(**request)
    set_runtime(inbox_repo, "v4")
    second = service.submit(**request)
    assert first["id"] == second["id"] and second["runtime"] == "v3"
    assert len(inbox_repo.list("alice", "message")) == 1
    assert second["request"]["message"] == "  合成原话\n "


@pytest.mark.parametrize("runtime", [True, [], "future"])
def test_invalid_owner_runtime_rolls_back_original_and_run(inbox_repo: PostgresRepository, runtime: Any) -> None:
    service, thread = ingress(inbox_repo)
    set_runtime(inbox_repo, runtime)
    with pytest.raises(EvidenceError):
        submit(service, thread)
    assert inbox_repo.list("alice", "message") == [] and inbox_repo.queued_runs("alice") == []


def test_caller_runtime_boolean_cannot_authorize_v4(inbox_repo: PostgresRepository) -> None:
    service, thread = ingress(inbox_repo)
    with pytest.raises(EvidenceError):
        submit(service, thread, runtime=True)
    assert inbox_repo.list("alice", "message") == []


def test_native_source_cannot_move_across_private_thread_or_owner(inbox_repo: PostgresRepository) -> None:
    service, thread = ingress(inbox_repo)
    source = service.receive(
        owner="alice", thread_id=thread, message="合成原话", request_id="first", source_id="native"
    )
    private = ThreadService(inbox_repo).create("alice", incognito=True, request_id="private")
    with pytest.raises(ScopeError):
        service.receive(
            owner="alice", thread_id=private["id"], message="合成原话", request_id="other", source_id="native"
        )
    other, other_thread = ingress(inbox_repo, owner="bob")
    with pytest.raises(ScopeError):
        other.queue(owner="bob", thread_id=other_thread, source_ids=[source["id"]], request_id="foreign")


def test_running_supplement_is_dormant_and_after_model_goes_next_turn(inbox_repo: PostgresRepository) -> None:
    set_runtime(inbox_repo, "v4")
    service, thread = ingress(inbox_repo)
    parent = submit(service, thread, "合成第一问")
    parent = inbox_repo.claim_run("alice", parent["id"])
    later = submit(service, thread, "合成补充")
    assert later["status"] == "inbox_wait" and later["request"]["inbox_parent_run_id"] == parent["id"]
    inbox = ThreadInbox(inbox_repo)
    assert inbox.claim(parent, phase="after_model", iteration=1) == ()
    assert inbox.claim(parent, phase="before_model", iteration=2) == ()
    inbox_repo.fail_run("alice", parent["id"], "合成失败", parent["lease_token"])
    assert inbox.recover("alice") == {"queued": 1, "consumed": 0, "revoked": 0}
    assert inbox_repo.fetch_run("alice", later["id"])["status"] == "queued"
    assert inbox.recover("alice") == {"queued": 0, "consumed": 0, "revoked": 0}


def test_before_model_claim_is_durable_idempotent_and_cannot_fake_ack(inbox_repo: PostgresRepository) -> None:
    set_runtime(inbox_repo, "v4")
    service, thread = ingress(inbox_repo)
    parent = inbox_repo.claim_run("alice", submit(service, thread)["id"])
    fallback = submit(service, thread, "合成补充原话")
    first = ThreadInbox(inbox_repo).claim(parent, phase="before_model", iteration=2)
    second = ThreadInbox(inbox_repo).claim(parent, phase="before_model", iteration=2)
    assert len(first) == 1 and first == second and first[0].user_messages[0].content == "合成补充原话"
    assert "合成补充原话" not in repr(first[0])
    with pytest.raises(EvidenceError, match="真实模型|已完成模型"):
        ThreadInbox(inbox_repo).ack(parent, first[0], model_seq=1)
    assert inbox_repo.fetch_run("alice", fallback["id"])["status"] == "inbox_wait"


def test_private_duplicate_does_not_extend_ttl_and_stays_private(inbox_repo: PostgresRepository) -> None:
    set_runtime(inbox_repo, "v4")
    service, thread = ingress(inbox_repo, private=True)
    request = dict(owner="alice", thread_id=thread, message="合成私密原话", request_id="same")
    first = service.submit(**request)
    before = ThreadService(inbox_repo).get("alice", thread)["expires_at"]
    get_clock().advance(timedelta(minutes=5))
    again = service.submit(**request)
    assert again["id"] == first["id"] and again["request"]["incognito"] is True
    assert ThreadService(inbox_repo).get("alice", thread)["expires_at"] == before
    assert inbox_repo.get("alice", "message", first["request"]["source_message_id"])["incognito"] is True


def test_notification_is_visible_only_after_complete_route_commit(inbox_repo: PostgresRepository) -> None:
    set_runtime(inbox_repo, "v4")
    service, thread = ingress(inbox_repo)
    with psycopg.connect(inbox_repo.dsn, autocommit=True) as listener:
        listener.execute("LISTEN mj_run_queued")
        with inbox_repo.transaction("alice"):
            run = submit(service, thread)
            row = listener.execute(
                sql.SQL("SELECT runtime FROM {} WHERE id=%s").format(inbox_repo.table("core_runs")), (run["id"],)
            ).fetchone()
            assert row is None
        notifications = list(listener.notifies(timeout=0.2))
        assert any(run["id"] in notice.payload for notice in notifications)
        row = listener.execute(
            sql.SQL("SELECT runtime,thread_id FROM {} WHERE id=%s").format(inbox_repo.table("core_runs")), (run["id"],)
        ).fetchone()
        assert row == ("v4", thread)


def test_claim_source_ceiling_keeps_overflow_as_next_turn(inbox_repo: PostgresRepository) -> None:
    set_runtime(inbox_repo, "v4")
    service, thread = ingress(inbox_repo)
    parent = inbox_repo.claim_run("alice", submit(service, thread)["id"])
    groups = []
    for count in (64, 40):
        sources = [
            service.receive(owner="alice", thread_id=thread, message="合成补充" + str(i), request_id=uuid.uuid4().hex)[
                "id"
            ]
            for i in range(count)
        ]
        groups.append(service.queue(owner="alice", thread_id=thread, source_ids=sources, request_id=uuid.uuid4().hex))
    claims = ThreadInbox(inbox_repo).claim(parent, phase="before_model", iteration=1)
    assert len(claims) == 1 and len(claims[0].versions) == 64
    overflow = inbox_repo.get("alice", "request", "thread-inbox:" + groups[1]["id"])
    assert overflow["inbox_state"] == "next_turn" and groups[1]["status"] == "inbox_wait"
    inbox_repo.fail_run("alice", parent["id"], "合成停止", parent["lease_token"])
    assert ThreadInbox(inbox_repo).recover("alice")["queued"] == 2

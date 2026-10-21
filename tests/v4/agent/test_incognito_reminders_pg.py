"""One real user approval retains text/time only; expiry preserves sent receipts."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.incognito_reminders import CONFIRM_QUESTION, IncognitoReminderService
from mingjing_core.application.private_retention import retire_private_thread
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_threads_private_pg import threads as source_threads


@pytest.fixture
def reminders(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> IncognitoReminderService:
    threads = source_threads.__wrapped__(p2_repo, monkeypatch)
    return IncognitoReminderService(p2_repo, clock=threads.clock)


def user_run(service: IncognitoReminderService, thread_id: str, text: str, request: str) -> dict:
    # These tests exercise reminder services without running AgentRuntime. End
    # the previous component fixture lease before the next user turn.
    with service.repo.transaction("alice") as connection:
        previous = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner='alice' AND thread_id=%s AND status='running'").format(
                service.repo.table("core_runs")
            ),
            (thread_id,),
        ).fetchall()
        for row in previous:
            service.repo.fail_run("alice", row["id"], "component-fixture-completed", row["lease_token"])
    message = service.threads.receive("alice", thread_id, text, request_id=request)
    run = service.repo.queue_run("alice", request, {"message": text, "source_message_id": message["id"]})
    with service.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id=%s WHERE id=%s").format(service.repo.table("core_runs")),
            (thread_id, run["id"]),
        )
    return service.repo.claim_run("alice", run["id"])


def begin(service: IncognitoReminderService) -> tuple[dict, dict, dict]:
    thread = service.threads.create("alice", incognito=True, request_id="private-reminder-synthetic")
    run = user_run(service, thread["id"], "请在2026-10-18 09:00提醒我带雨伞，这里还有不保存的合成私密正文", "first")
    pending = service.begin("alice", run, text="带雨伞", due_at="2026-10-18T09:00:00+08:00")
    return thread, run, pending


def test_explicit_request_asks_once_and_leaves_no_reminder_before_approval(reminders: IncognitoReminderService) -> None:
    _, run, pending = begin(reminders)
    assert pending["asked"]["question"] == CONFIRM_QUESTION
    repeated = reminders.begin("alice", run, text="带雨伞", due_at="2026-10-18T09:00:00+08:00")
    assert repeated["status"] == "already_asked" and repeated["asked"] is None
    assert reminders.repo.list("alice", "reminder") == []
    with pytest.raises(EvidenceError, match="之后"):
        reminders.confirm("alice", run, request_id=pending["request_id"])


@pytest.mark.parametrize("answer", ["同意", "可以", "确认。", "yes"])
def test_only_approved_text_and_time_leave_the_private_thread(reminders: IncognitoReminderService, answer: str) -> None:
    thread, _, pending = begin(reminders)
    run = user_run(reminders, thread["id"], answer, "confirm")
    receipt = reminders.confirm("alice", run, request_id=pending["request_id"])
    assert receipt["write_status"] == "saved"
    assert reminders.confirm("alice", run, request_id=pending["request_id"])["id"] == receipt["id"]
    row = reminders.repo.get("alice", "reminder", receipt["id"])
    assert row["source"] == "incognito_explicit" and row["text"] == "带雨伞"
    assert row["due_at"] == "2026-10-18T01:00:00+00:00"
    assert not set(row).intersection({"thread_id", "source_ids", "source_refs", "run_id", "confirmation_text"})
    assert "合成私密正文" not in str(row) and reminders.repo.list("alice", "fact") == []
    reminders.clock.advance(timedelta(hours=25))
    retire_private_thread(reminders.repo, "alice", thread["id"], clock=reminders.clock)
    assert reminders.repo.get("alice", "reminder", receipt["id"])["status"] == "active"


@pytest.mark.parametrize(
    "answer,status",
    [
        ("不保存", "rejected"),
        ("不同意", "rejected"),
        ("我考虑一下", "pending_confirm"),
        ("他说“同意”", "pending_confirm"),
        ("同意，但不要保存", "pending_confirm"),
    ],
)
def test_refusal_and_ambiguous_reply_do_not_save(reminders: IncognitoReminderService, answer: str, status: str) -> None:
    thread, _, pending = begin(reminders)
    run = user_run(reminders, thread["id"], answer, "confirm")
    assert reminders.confirm("alice", run, request_id=pending["request_id"])["write_status"] == status
    assert reminders.repo.list("alice", "reminder") == []


def test_changed_origin_and_nonuser_reply_cannot_authorize(reminders: IncognitoReminderService) -> None:
    thread, original, pending = begin(reminders)
    run = user_run(reminders, thread["id"], "同意", "confirm")
    source = reminders.threads.memory.get_source("alice", run["request"]["source_message_id"])
    reminders.repo.update("alice", "message", source["id"], {"role": "assistant"}, expected_revision=source["revision"])
    with pytest.raises(EvidenceError):
        reminders.confirm("alice", run, request_id=pending["request_id"])
    source = reminders.threads.memory.get_source("alice", original["request"]["source_message_id"])
    reminders.repo.update(
        "alice", "message", source["id"], {"content": "改变原始请求"}, expected_revision=source["revision"]
    )
    run = user_run(reminders, thread["id"], "同意", "another-confirm")
    with pytest.raises(EvidenceError, match="改变"):
        reminders.confirm("alice", run, request_id=pending["request_id"])


def seed_sent(service: IncognitoReminderService, ident: str, *, status: str = "sent") -> None:
    with service.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL(
                "INSERT INTO {}(id,owner,subject,business_id,channel,target,status,receipt,payload,updated_at) "
                "VALUES('synthetic-sent','alice','self',%s,'synthetic','synthetic',%s,'synthetic-receipt',%s,%s)"
            ).format(service.repo.table("delivery_outbox")),
            ("reminder:" + ident, status, Jsonb({"text": "带雨伞"}), service.clock.now()),
        )


def test_seven_day_cleanup_requires_sent_proof_and_clears_payload_without_resending(
    reminders: IncognitoReminderService,
) -> None:
    thread, _, pending = begin(reminders)
    run = user_run(reminders, thread["id"], "同意", "confirm")
    receipt = reminders.confirm("alice", run, request_id=pending["request_id"])
    row = reminders.repo.get("alice", "reminder", receipt["id"])
    with pytest.raises(EvidenceError, match="收据"):
        reminders.delivered("alice", row["id"], outbox_id="absent", expected_revision=row["revision"])
    seed_sent(reminders, row["id"])
    delivered = reminders.delivered("alice", row["id"], outbox_id="synthetic-sent", expected_revision=row["revision"])
    assert reminders.cleanup_delivered("alice") == 0
    reminders.clock.advance(timedelta(days=7))
    assert reminders.cleanup_delivered("alice") == 1 and reminders.cleanup_delivered("alice") == 0
    retired = reminders.repo.get("alice", "reminder", row["id"], include_deleted=True)
    assert retired["status"] == "deleted" and "text" not in retired
    assert datetime.fromisoformat(delivered["delete_after"]) - datetime.fromisoformat(
        delivered["delivered_at"]
    ) == timedelta(days=7)
    with reminders.repo.transaction("alice") as connection:
        outbox = connection.execute(
            sql.SQL("SELECT status,receipt,payload FROM {} WHERE id='synthetic-sent'").format(
                reminders.repo.table("delivery_outbox")
            )
        ).fetchone()
    assert outbox == dict(status="sent", receipt="synthetic-receipt", payload={})

"""Real PG mode state and native-event receipts are isolated and replay safe."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from mingjing_core.application.privacy_mode import PrivacyModeService
from mingjing_core.application.privacy_run_barrier import run_persistence_blocked
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_thread_inbox_pg import set_runtime


@pytest.fixture(name="privacy_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    p2_repo.bind_channel("alice", "feishu", "ou_syntheticAlice")
    p2_repo.bind_channel("alice", "web", "author")
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def receive(repo: PostgresRepository, text: str, request: str, **kwargs: Any) -> dict[str, Any]:
    owner, subject = kwargs.pop("owner", "alice"), kwargs.pop("subject", "self")
    thread = ThreadService(repo).create(owner, subject=subject, request_id="life:" + subject)
    return PrivacyModeService(repo).receive(
        owner=owner, subject=subject, thread_id=thread["id"], message=text, request_id=request, **kwargs
    )


def test_entry_routes_before_commit_and_followups_never_enter_life(privacy_repo: PostgresRepository) -> None:
    set_runtime(privacy_repo, "v4")
    first = receive(privacy_repo, "开个无痕，我有合成私密问题", "enter")
    second = receive(privacy_repo, "合成的后续问题", "follow")
    assert first["thread_id"].startswith("incognito:") and second["thread_id"] == first["thread_id"]
    assert all(
        row["incognito"] and row["policy"]["persist_allowed"] is False for row in privacy_repo.list("alice", "message")
    )
    assert ThreadService(privacy_repo).history("alice", "life:self") == []
    assert privacy_repo.search("alice", "self", ["合成"], ["message"]) == []
    receipts = privacy_repo.list("alice", "request")
    assert all("合成私密问题" not in str(row) for row in receipts)


def test_mode_is_isolated_by_owner_subject_channel_and_conversation(privacy_repo: PostgresRepository) -> None:
    set_runtime(privacy_repo, "v4")
    privacy_repo.create_subject("alice", "relative", "合成人物")
    receive(privacy_repo, "这段别记", "entry", conversation_id="one")
    assert receive(privacy_repo, "合成后续", "follow", conversation_id="one")["incognito"] is True
    others = [
        receive(privacy_repo, "合成普通", "other-conversation", conversation_id="two"),
        receive(
            privacy_repo,
            "合成普通",
            "other-channel",
            conversation_id="one",
            channel="feishu",
            external_id="ou_syntheticAlice",
        ),
        receive(privacy_repo, "合成普通", "other-owner", owner="bob", conversation_id="one"),
        receive(privacy_repo, "合成普通", "other-subject", subject="relative", conversation_id="one"),
    ]
    assert all(row.get("incognito", False) is False for row in others)


def test_exit_is_explicit_and_does_not_move_previous_original(privacy_repo: PostgresRepository) -> None:
    set_runtime(privacy_repo, "v4")
    private = receive(privacy_repo, "开个无痕", "entry")
    assert receive(privacy_repo, "他说：结束无痕", "quoted")["thread_id"] == private["thread_id"]
    ended = receive(privacy_repo, "结束无痕", "exit")
    assert ended["thread_id"] == "life:self"
    assert receive(privacy_repo, "合成新的普通问题", "normal")["thread_id"] == "life:self"
    assert privacy_repo.get("alice", "message", private["id"])["thread_id"] == private["thread_id"]
    replay = receive(privacy_repo, "开个无痕", "entry")
    assert replay["id"] == private["id"]
    assert receive(privacy_repo, "重放不会重新进入私密", "after-replay")["thread_id"] == "life:self"


def test_24_hour_inactivity_expires_mode_and_duplicate_does_not_touch(privacy_repo: PostgresRepository) -> None:
    set_runtime(privacy_repo, "v4")
    first = receive(privacy_repo, "开个无痕", "entry")
    expiry = ThreadService(privacy_repo).get("alice", first["thread_id"])["expires_at"]
    get_clock().advance(timedelta(hours=23))
    assert receive(privacy_repo, "开个无痕", "entry")["id"] == first["id"]
    assert ThreadService(privacy_repo).get("alice", first["thread_id"])["expires_at"] == expiry
    get_clock().advance(timedelta(hours=1))
    assert receive(privacy_repo, "合成普通问题", "expired-next")["thread_id"] == "life:self"
    with pytest.raises(EvidenceError, match="到期"):
        receive(privacy_repo, "开个无痕", "entry")
    newer = receive(privacy_repo, "开个无痕", "entry-new")
    assert newer["thread_id"] != first["thread_id"]


def test_same_native_event_cannot_change_route_text_author_or_conversation(privacy_repo: PostgresRepository) -> None:
    set_runtime(privacy_repo, "v4")
    first = receive(privacy_repo, "开个无痕", "entry", source_id="native-event", external_id="author")
    for changes in ({"conversation_id": "other"}, {"external_id": "forged"}):
        with pytest.raises(EvidenceError, match="替换"):
            receive(privacy_repo, "开个无痕", "different-request", source_id="native-event", **changes)
    with pytest.raises(EvidenceError, match="替换"):
        receive(privacy_repo, "合成替换正文", "entry", source_id="native-event", external_id="author")
    assert privacy_repo.list("alice", "message")[0]["id"] == first["id"]


def test_existing_native_life_source_cannot_be_imported_as_private(privacy_repo: PostgresRepository) -> None:
    set_runtime(privacy_repo, "v4")
    receive(privacy_repo, "合成普通原话", "normal", source_id="native")
    receive(privacy_repo, "开个无痕", "entry")
    with pytest.raises(EvidenceError, match="替换"):
        receive(privacy_repo, "合成普通原话", "normal", source_id="native", conversation_id="other")


def test_same_event_in_different_offsets_is_same_instant_without_host_timezone(
    privacy_repo: PostgresRepository,
) -> None:
    set_runtime(privacy_repo, "v4")
    stamp = datetime(2026, 10, 17, 0, tzinfo=UTC)
    first = receive(privacy_repo, "开个无痕", "timezone", at=stamp)
    again = receive(privacy_repo, "开个无痕", "timezone", at=stamp.astimezone(timezone(timedelta(hours=8))))
    assert first["id"] == again["id"]
    with pytest.raises(EvidenceError, match="带时区"):
        receive(privacy_repo, "合成原话", "naive", at=stamp.replace(tzinfo=None))


def test_v3_private_command_has_zero_messages_and_zero_runs(privacy_repo: PostgresRepository) -> None:
    for text in ("这段别记", "开个无痕", "结束无痕"):
        with pytest.raises(EvidenceError, match="尚未保存"):
            receive(privacy_repo, text, text)
    assert privacy_repo.list("alice", "message") == [] and privacy_repo.queued_runs() == []
    assert receive(privacy_repo, "朋友说，开个无痕", "ordinary")["thread_id"] == "life:self"


def test_legacy_gate_preserves_active_automatic_privacy_and_releases_after_expiry(
    privacy_repo: PostgresRepository,
) -> None:
    service = PrivacyModeService(privacy_repo)
    service.assert_legacy_safe("alice", "self", "合成普通问题")
    with pytest.raises(EvidenceError, match="尚未保存"):
        service.assert_legacy_safe("alice", "self", "开个无痕")
    set_runtime(privacy_repo, "v4")
    receive(privacy_repo, "开个无痕", "private")
    set_runtime(privacy_repo, "v3")
    with pytest.raises(EvidenceError, match="尚未保存"):
        service.assert_legacy_safe("alice", "self", "合成后续问题")
    get_clock().advance(timedelta(hours=24))
    service.assert_legacy_safe("alice", "self", "合成新的普通问题")


def test_optout_blocks_existing_run_using_pg_authority_not_stale_usage(privacy_repo: PostgresRepository) -> None:
    set_runtime(privacy_repo, "v4")
    source = receive(privacy_repo, "我喜欢合成夜班", "normal")
    old = privacy_repo.queue_run(
        "alice", "run-before-optout", {"message": source["content"], "source_message_id": source["id"]}
    )
    assert run_persistence_blocked(privacy_repo, old) is False
    receive(privacy_repo, "本轮别记", "control")
    assert run_persistence_blocked(privacy_repo, old) is True
    claimed = privacy_repo.claim_run("alice", old["id"])
    privacy_repo.fail_run("alice", old["id"], "合成重试", claimed["lease_token"], status="stale")
    retried = privacy_repo.prepare_retry("alice", old["id"])["run"]
    assert retried["retry_epoch"] == old["retry_epoch"] + 1 and run_persistence_blocked(privacy_repo, retried)
    with pytest.raises(ScopeError):
        run_persistence_blocked(privacy_repo, dict(old, owner="bob"))
    assert privacy_repo.list("alice", "fact") == []

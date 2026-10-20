"""Natural commands route web/Feishu before persistence, including delayed batches."""

from __future__ import annotations

from datetime import timedelta

import pytest

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.feishu_ingress import FeishuIngress
from mingjing_core.application.privacy_run_barrier import run_persistence_blocked
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_feishu_ingress_pg import receive as feishu_receive
from .test_privacy_mode_pg import repository_fixture as privacy_repo
from .test_thread_inbox_pg import set_runtime

__all__ = ["privacy_repo"]


def test_web_submit_queues_actual_private_thread_and_duplicate_retains_it(privacy_repo: PostgresRepository) -> None:
    set_runtime(privacy_repo, "v4")
    threads = ThreadService(privacy_repo)
    thread = threads.create("alice", request_id="life")
    ingress = ThreadIngress(ConsultationService(privacy_repo))
    values = dict(owner="alice", thread_id=thread["id"], message="这段别记", request_id="private")
    run = ingress.submit(**values)
    assert run["thread_id"].startswith("incognito:") and run["request"]["incognito"] is True
    assert run["request"]["thread_id"] == run["thread_id"] and run["calls"] == 0
    assert ingress.submit(**values)["id"] == run["id"]
    assert threads.history("alice", "life:self") == []


def test_private_case_binding_rolls_back_original_mode_and_run(privacy_repo: PostgresRepository) -> None:
    set_runtime(privacy_repo, "v4")
    threads = ThreadService(privacy_repo)
    thread = threads.create("alice", request_id="life")
    ingress = ThreadIngress(ConsultationService(privacy_repo))
    with pytest.raises(EvidenceError, match="长期事项"):
        ingress.submit(
            owner="alice", thread_id=thread["id"], message="开个无痕", request_id="bad", case_ids=["untrusted-case"]
        )
    assert privacy_repo.list("alice", "message") == [] and privacy_repo.queued_runs() == []
    assert privacy_repo.list("alice", "session") == []
    normal = ingress.submit(owner="alice", thread_id=thread["id"], message="合成普通", request_id="next")
    assert normal["thread_id"] == "life:self"


def test_feishu_private_commands_merge_in_actual_private_thread_and_other_chat_stays_life(
    privacy_repo: PostgresRepository,
) -> None:
    set_runtime(privacy_repo, "v4")
    ingress = FeishuIngress(ConsultationService(privacy_repo))
    first = feishu_receive(ingress, "om_private", "开个无痕")
    second = feishu_receive(ingress, "om_follow", "合成后续问题", offset=1)
    other = feishu_receive(ingress, "om_other", "合成普通问题", chat="other-chat")
    get_clock().advance(timedelta(milliseconds=2500))
    private = privacy_repo.fetch_run("alice", ingress.flush("alice", first["inbound_id"])["run_id"])
    assert private["thread_id"].startswith("incognito:") and private["request"]["incognito"] is True
    assert len(private["request"]["source_message_ids"]) == 2
    assert privacy_repo.get("alice", "request", second["inbound_id"])["run_id"] == private["id"]
    ordinary = privacy_repo.fetch_run("alice", ingress.flush("alice", other["inbound_id"])["run_id"])
    assert ordinary["thread_id"] == "life:self"


def test_buffered_pre_optout_feishu_original_gets_barrier_before_notifying_queue(
    privacy_repo: PostgresRepository,
) -> None:
    set_runtime(privacy_repo, "v4")
    ingress = FeishuIngress(ConsultationService(privacy_repo))
    before = feishu_receive(ingress, "om_before", "我喜欢合成夜班")
    feishu_receive(ingress, "om_control", "本轮别记", offset=1)
    assert privacy_repo.queued_runs() == []
    get_clock().advance(timedelta(milliseconds=2500))
    old_run = privacy_repo.fetch_run("alice", ingress.flush("alice", before["inbound_id"])["run_id"])
    assert old_run["thread_id"] == "life:self" and run_persistence_blocked(privacy_repo, old_run)
    feishu_receive(ingress, "om_exit", "结束无痕", offset=2)
    get_clock().advance(timedelta(milliseconds=2500))
    later = feishu_receive(ingress, "om_new_life", "合成新的普通偏好", offset=3)
    get_clock().advance(timedelta(milliseconds=2500))
    new_run = privacy_repo.fetch_run("alice", ingress.flush("alice", later["inbound_id"])["run_id"])
    assert new_run["thread_id"] == "life:self" and not run_persistence_blocked(privacy_repo, new_run)


def test_duplicate_native_event_after_exit_does_not_move_source_or_reactivate_private(
    privacy_repo: PostgresRepository,
) -> None:
    set_runtime(privacy_repo, "v4")
    ingress = FeishuIngress(ConsultationService(privacy_repo))
    first = feishu_receive(ingress, "om_entry", "开个无痕")
    first_source = privacy_repo.get("alice", "request", first["inbound_id"])["source_id"]
    private = privacy_repo.get("alice", "message", first_source)["thread_id"]
    feishu_receive(ingress, "om_exit", "结束无痕", offset=1)
    assert feishu_receive(ingress, "om_entry", "开个无痕")["inbound_id"] == first["inbound_id"]
    next_item = feishu_receive(ingress, "om_next", "合成普通问题", offset=2)
    assert privacy_repo.get("alice", "message", first_source)["thread_id"] == private
    next_source = privacy_repo.get("alice", "request", next_item["inbound_id"])["source_id"]
    assert privacy_repo.get("alice", "message", next_source)["thread_id"] == "life:self"

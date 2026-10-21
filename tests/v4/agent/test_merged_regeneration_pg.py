"""Merged-source withdrawals rebuild one real runtime epoch without restoring bodies."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.agent_regeneration import AgentRegenerator
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.thread_inbox import ThreadInbox
from mingjing_core.application.thread_sources import source_segments
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.models.port import StreamEvent, ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_agent_runtime_pg import invoke
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_thread_inbox_pg import ingress, set_runtime, submit


@pytest.fixture(name="merged_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def merged(repo: PostgresRepository, texts: list[str]) -> tuple[dict, list[dict]]:
    set_runtime(repo, "v4")
    intake, thread = ingress(repo)
    sources = []
    for index, text in enumerate(texts):
        sources.append(intake.receive(owner="alice", thread_id=thread, message=text, request_id="source-" + str(index)))
        get_clock().advance(timedelta(milliseconds=1))
    run = intake.queue(owner="alice", thread_id=thread, source_ids=[row["id"] for row in sources], request_id="merged")
    return repo.claim_run("alice", run["id"], lease_seconds=150), sources


def source_fact(repo: PostgresRepository, source: dict[str, Any]) -> dict[str, Any]:
    return MemoryService(repo).save_fact("alice", "self", source["id"], source["content"], "preference")


class WithdrawOnce(ScriptedPort):
    def __init__(self, action: Any) -> None:
        super().__init__([answer("失效的旧草稿〔m1〕"), answer("干净的新合成回答")])
        self.action = action

    def stream(self, messages: Any, **kwargs: Any) -> Iterator[StreamEvent]:
        if not self.requests:
            self.requests.append({"messages": copy.deepcopy(messages)})
            self.action()
            yield StreamEvent("text", "失效的旧草稿〔m1〕")
            return
        yield from super().stream(messages, **kwargs)


@pytest.mark.parametrize("scope", ["source", "fact"])
def test_auxiliary_withdrawal_keeps_primary_and_rebuilds_exact_sources_once(
    merged_repo: PostgresRepository,
    scope: str,
) -> None:
    repo, memory = merged_repo, MemoryService(merged_repo)
    run, sources = merged(repo, ["我喜欢已撤销的合成夜班", "我喜欢仍有效的合成清单", "现在请给合成建议"])
    fact = source_fact(repo, sources[0])
    port = WithdrawOnce(
        lambda: memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope=scope)
    )
    result, events = invoke(repo, run, port)
    current = repo.fetch_run("alice", run["id"])
    assert result["text"] == "干净的新合成回答" and len(port.requests) == 2 and current["retry_epoch"] == 1
    assert current["usage"]["agent_runtime"]["regenerations"] == 1
    expected = sources[1:]
    assert current["request"]["source_message_ids"] == [row["id"] for row in expected]
    assert current["request"]["source_segments"] == source_segments(expected)
    fresh = json.dumps([message.content for message in port.requests[1]["messages"]], ensure_ascii=False)
    assert sources[0]["content"] not in fresh and "失效的旧草稿" not in fresh
    assert sources[1]["content"] in fresh and sources[2]["content"] in fresh
    snapshot = repo.get("alice", "runtime_step", f"{run['id']}:e1:agent_initial_context")
    forbidden_aliases = {fact["id"], sources[0]["id"]} if scope == "source" else {fact["id"]}
    assert not any(item["id"] in forbidden_aliases for item in snapshot["output"]["alias_map"].values())
    reply = repo.get("alice", "message", result["message_id"])
    if scope == "source":
        assert sources[0]["id"] not in reply["source_ids"]
    assert any(event["type"] == "text_reset" and event["data"]["text"] == "" for event in events)


@pytest.mark.parametrize("scope", ["source", "fact"])
def test_primary_whole_or_partial_withdrawal_still_has_no_new_epoch_or_final(
    merged_repo: PostgresRepository,
    scope: str,
) -> None:
    repo, memory = merged_repo, MemoryService(merged_repo)
    run, sources = merged(repo, ["我喜欢合成普通清单", "我喜欢主问题的合成夜班"])
    fact = source_fact(repo, sources[-1])
    port = WithdrawOnce(
        lambda: memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope=scope)
    )
    with pytest.raises(CoreError):
        invoke(repo, run, port)
    current = repo.fetch_run("alice", run["id"])
    assert current["retry_epoch"] == 0 and current["result"] is None and len(port.requests) == 1
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]


def test_cancellation_cannot_escape_through_related_auxiliary_withdrawal(merged_repo: PostgresRepository) -> None:
    repo, memory = merged_repo, MemoryService(merged_repo)
    run, sources = merged(repo, ["我喜欢待撤回的合成夜班", "合成的主问题"])
    fact = source_fact(repo, sources[0])

    def cancel_and_withdraw() -> None:
        DispatcherCancellation(repo).request("alice", run["id"])
        memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")

    port = WithdrawOnce(cancel_and_withdraw)
    with pytest.raises(CoreError):
        invoke(repo, run, port)
    current = repo.fetch_run("alice", run["id"])
    assert current["cancel_requested_at"] is not None and current["retry_epoch"] == 0 and current["result"] is None


@pytest.mark.parametrize("mutation", ["source_list", "source_range", "primary_text"])
def test_deleted_request_cannot_trust_tampered_caller_source_list(
    merged_repo: PostgresRepository,
    mutation: str,
) -> None:
    repo = merged_repo
    run, sources = merged(repo, ["我喜欢原合成夜班", "合成主问题"])
    forged = copy.deepcopy(run)
    if mutation == "source_list":
        forged["request"]["source_message_ids"] = [sources[-1]["id"]]
        forged["request"]["source_segments"] = source_segments([sources[-1]])
    elif mutation == "source_range":
        forged["request"]["source_segments"][0]["end"] += 1
    else:
        forged["request"]["message"] = "被篡改的主问题"
    repo.set_run_dependencies(
        "alice", run["id"], {"message:" + row["id"]: row["revision"] for row in sources}, run["lease_token"]
    )
    fact = source_fact(repo, sources[0])
    MemoryService(repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    error = "原始持久请求证明" if mutation == "primary_text" else "入队区间的持久证明"
    with repo.transaction("alice") as connection, pytest.raises(EvidenceError, match=error):
        current = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE id=%s").format(repo.table("core_runs")), (run["id"],)
        ).fetchone()
        assert current["request"] == {}
        AgentRegenerator(repo)._proven_request(connection, current, forged)


def test_nonwithdrawal_version_change_is_not_hidden_by_rebinding(merged_repo: PostgresRepository) -> None:
    repo, memory = merged_repo, MemoryService(merged_repo)
    background = memory.receive("alice", content="我喜欢另一个撤销合成旧资料", source_id="old-background")
    fact = source_fact(repo, background)
    get_clock().advance(timedelta(milliseconds=1))
    run, sources = merged(repo, ["我喜欢仍有效的合成夜班", "合成主问题"])

    def modify_and_withdraw() -> None:
        repo.update(
            "alice", "message", sources[0]["id"], {"synthetic_marker": True}, expected_revision=sources[0]["revision"]
        )
        memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")

    port = WithdrawOnce(modify_and_withdraw)
    with pytest.raises(EvidenceError, match="非撤销"):
        invoke(repo, run, port)
    assert repo.fetch_run("alice", run["id"])["retry_epoch"] == 0 and len(port.requests) == 1


@pytest.mark.parametrize("withdraw_supplement", [True, False])
def test_old_adoption_is_not_reused_in_new_epoch_and_valid_supplement_falls_back(
    merged_repo: PostgresRepository,
    withdraw_supplement: bool,
) -> None:
    repo, memory = merged_repo, MemoryService(merged_repo)
    background = memory.receive("alice", content="我喜欢用于撤回的合成旧资料", source_id="old-background")
    old = source_fact(repo, background)
    get_clock().advance(timedelta(milliseconds=1))
    set_runtime(repo, "v4")
    intake, thread = ingress(repo)
    parent = repo.claim_run("alice", submit(intake, thread, "合成主问题")["id"])
    port = ScriptedPort(
        [
            answer("", [ToolCall("clock-one", "time_context", {})]),
            answer("", [ToolCall("clock-two", "time_context", {})]),
            answer("干净的补充撤销后回答"),
        ]
    )
    received, facts = [], []

    def observe(event: dict[str, Any]) -> None:
        if event["type"] != "tool_result" or event["data"]["name"] != "time_context":
            return
        if not received:
            fallback = submit(intake, thread, "我喜欢已采用的合成补充偏好")
            received.append(fallback)
            facts.append(source_fact(repo, repo.get("alice", "message", fallback["request"]["source_message_id"])))
            return
        item = repo.get("alice", "request", "thread-inbox:" + received[0]["id"])
        assert item["inbox_state"] == "adopted" and item["adoption"]["epoch"] == 0
        target = facts[0] if withdraw_supplement else old
        memory.retire_fact("alice", target["id"], expected_revision=target["revision"], scope="source")

    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        intake.service, "alice", parent["id"], parent["lease_token"], observe
    )
    current = repo.fetch_run("alice", parent["id"])
    assert result["text"] == "干净的补充撤销后回答" and current["retry_epoch"] == 1 and len(port.requests) == 3
    fresh = json.dumps([message.content for message in port.requests[-1]["messages"]], ensure_ascii=False)
    assert "我喜欢已采用的合成补充偏好" not in fresh
    if not withdraw_supplement:
        assert old["content"] not in fresh
    assert received[0]["request"]["source_message_id"] not in current["request"]["source_message_ids"]
    ThreadInbox(repo).recover("alice")
    fallback_status = repo.fetch_run("alice", received[0]["id"])["status"]
    assert fallback_status == ("revoked" if withdraw_supplement else "queued")

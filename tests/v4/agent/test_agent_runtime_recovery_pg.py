"""Recovery tests keep real source withdrawal and step replay authoritative."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_review_proofs import ReviewProofStore
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import StreamEvent
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_agent_runtime_pg import invoke, queued
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, modify
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="runtime_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def fact(repo: PostgresRepository, marker: str = "已撤回的合成旧资料") -> dict[str, Any]:
    memory = MemoryService(repo)
    old = memory.receive("alice", content=marker, source_id=marker, at=get_clock().now())
    return memory.save_fact("alice", "self", old["id"], marker, "preference")


def test_withdrawal_creates_one_clean_epoch_without_restoring_old_private_body(
    runtime_repo: PostgresRepository,
) -> None:
    repo, memory = runtime_repo, MemoryService(runtime_repo)
    old = fact(repo)
    run = queued(repo, "现在请给合成建议")

    class WithdrawPort(ScriptedPort):
        def stream(self, messages: Any, **kwargs: Any) -> Iterator[StreamEvent]:
            if not self.requests:
                memory.retire_fact("alice", old["id"], expected_revision=old["revision"], scope="source")
                self.requests.append({"messages": messages})
                yield StreamEvent("text", "已经失效的合成草稿")
                return
            yield from super().stream(messages, **kwargs)

    port = WithdrawPort([answer("失效"), answer("干净的新答复")])
    result, events = invoke(repo, run, port)
    assert result["text"] == "干净的新答复" and len(port.requests) == 2
    current = repo.fetch_run("alice", run["id"])
    assert current["retry_epoch"] == 1 and current["usage"]["agent_runtime"]["regenerations"] == 1
    fresh_request = json.dumps([row.content for row in port.requests[1]["messages"]], ensure_ascii=False)
    assert old["content"] not in fresh_request and "已经失效的合成草稿" not in fresh_request
    for row in repo.list("alice", "runtime_step", include_deleted=True):
        if ":e0:" in row["id"]:
            assert row["status"] == "deleted" and not row.get("output")
    assert any(row["type"] == "text_reset" and row["data"]["text"] == "" for row in events)


def test_current_user_withdrawal_never_reconstitutes_original_request(runtime_repo: PostgresRepository) -> None:
    repo, memory = runtime_repo, MemoryService(runtime_repo)
    run = queued(repo)
    current = memory.save_fact(
        "alice", "self", run["request"]["source_message_id"], run["request"]["message"], "preference"
    )

    class WithdrawCurrent(ScriptedPort):
        def stream(self, messages: Any, **kwargs: Any) -> Iterator[StreamEvent]:
            memory.retire_fact("alice", current["id"], expected_revision=current["revision"], scope="source")
            yield StreamEvent("text", "不能发布")

    with pytest.raises(CoreError):
        invoke(repo, run, WithdrawCurrent([]))
    stored = repo.fetch_run("alice", run["id"])
    assert stored["status"] == "revoked" and stored["request"] == {} and stored["retry_epoch"] == 0
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]


def test_crash_before_commit_replays_completed_model_without_physical_request(
    runtime_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, run = runtime_repo, queued(runtime_repo)
    original = AgentFinalizer.finalize

    def crash(*args: Any, **kwargs: Any) -> Any:
        raise SystemExit("synthetic crash before final commit")

    monkeypatch.setattr(AgentFinalizer, "finalize", crash)
    with pytest.raises(SystemExit):
        invoke(repo, run, ScriptedPort([answer("待恢复的合成回答")]))
    monkeypatch.setattr(AgentFinalizer, "finalize", original)
    modify(repo, run, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", run["id"], lease_seconds=150)
    port = ScriptedPort([])
    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], reclaimed["lease_token"]
    )
    assert result["text"] == "待恢复的合成回答" and port.requests == []
    assert result["usage"]["model_streams_this_execution"] == 0
    assert result["usage"]["replayed_model_steps"] == 1


@pytest.mark.parametrize(
    "critic_text",
    [
        "not-json",
        '{"verdict":"pass","issues":[]}',
        '{"verdict":"revise","issues":[{"type":"fatalism","quote":"初稿里不存在","severity":5,"fix_hint":"修订"}]}',
    ],
)
def test_independent_critic_success_or_fail_open_never_invents_revision(
    runtime_repo: PostgresRepository, critic_text: str
) -> None:
    repo, run = runtime_repo, queued(runtime_repo)
    primary, critic = ScriptedPort([answer("受控的普通回答")]), ScriptedPort([answer(critic_text)])
    result, _ = invoke(repo, run, primary, critic=critic)
    expected = "passed" if '"pass"' in critic_text else "skipped"
    assert result["review"]["state"] == expected and result["text"] == "受控的普通回答"
    assert len(primary.requests) == 1 and len(critic.requests) == 1
    assert result["usage"]["model_steps"] == 2


def test_forged_trusted_receipt_cannot_change_actual_critic_public_value(
    runtime_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, run = runtime_repo, queued(runtime_repo)
    original = ReviewProofStore.save

    def forged(self: ReviewProofStore, *args: Any, **kwargs: Any) -> Any:
        receipt = original(self, *args, **kwargs)
        return replace(receipt, value={"state": "revised", "reasons": [], "revision_id": "invented"})

    monkeypatch.setattr(ReviewProofStore, "save", forged)
    with pytest.raises(CoreError):
        invoke(
            repo,
            run,
            ScriptedPort([answer("受控的普通回答")]),
            critic=ScriptedPort([answer('{"verdict":"pass","issues":[]}')]),
        )
    assert repo.fetch_run("alice", run["id"])["result"] is None
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]

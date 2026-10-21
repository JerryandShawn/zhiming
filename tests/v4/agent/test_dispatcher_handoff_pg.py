"""A private stack callback moves one lease; public events never carry lease tokens."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher import AgentDispatcher
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.dispatcher_notifications import RunSignals
from mingjing_core.application.dispatcher_service import DispatcherServiceProxy
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import LeaseConflict
from mingjing_core.models.port import StreamEvent
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_dispatcher_pg import queued, until
from .test_dispatcher_pg import repository_fixture as source_repo_fixture
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter


@pytest.fixture(name="dispatch_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Any:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def test_clean_epoch_then_cancel_uses_handed_off_lease(dispatch_repo: PostgresRepository) -> None:
    repo, memory, signals = dispatch_repo, MemoryService(dispatch_repo), RunSignals()
    old = memory.receive("alice", content="即将撤回的合成资料", source_id="old", at=get_clock().now())
    old_fact = memory.save_fact("alice", "self", old["id"], old["content"], "preference")
    run = queued(repo)

    class WithdrawThenCancel(ScriptedPort):
        def stream(self, messages: Any, **kwargs: Any) -> Any:
            self.requests.append({"messages": messages})
            if len(self.requests) == 1:
                memory.retire_fact("alice", old_fact["id"], expected_revision=old_fact["revision"], scope="source")
                yield StreamEvent("text", "无效旧草稿")
                return
            yield StreamEvent("text", "新批次中断正文")
            DispatcherCancellation(repo, signals).request("alice", run["id"])
            yield StreamEvent("done", {})

    runtime = AgentRuntime(
        repo, WithdrawThenCancel([]), SyntheticMeter(), offline=True, control_factory=signals.controls
    )
    dispatcher = AgentDispatcher(SimpleNamespace(repo=repo, runtime=runtime), signals=signals)
    try:
        assert dispatcher.tick() == 1
        until(lambda: repo.fetch_run("alice", run["id"])["status"] == "cancelled")
        current = repo.fetch_run("alice", run["id"])
        assert current["retry_epoch"] == 1 and current["lease_token"] is None and current["result"] is None
        partial = [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]
        assert len(partial) == 1 and partial[0]["content"] == "新批次中断正文"
        with repo.transaction("alice") as connection:
            events = connection.execute(
                sql.SQL("SELECT payload FROM {} WHERE run_id=%s").format(repo.table("core_run_events")), (run["id"],)
            ).fetchall()
        assert "lease_token" not in json.dumps(events)
    finally:
        dispatcher.close()


def test_handoff_rejects_forged_owner_token_and_repeated_epoch(dispatch_repo: PostgresRepository) -> None:
    repo, run = dispatch_repo, queued(dispatch_repo)
    run = repo.claim_run("alice", run["id"])
    proxy = DispatcherServiceProxy(SimpleNamespace(repo=repo), run)
    for forged in (dict(run, owner="bob"), dict(run, lease_token="invented"), dict(run, retry_epoch=2)):
        with pytest.raises(LeaseConflict):
            proxy.agent_lease_changed(run, forged)
    assert proxy.run["lease_token"] == run["lease_token"]

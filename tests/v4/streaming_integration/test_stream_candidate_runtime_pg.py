"""Original pure coalescer is consumed by actual Runtime, Journal, request ledger and PG."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.run_event_stream_state import STATE_KEY
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.models.port import ChatMessage, ModelPort, StreamEvent, ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval.targets.v4_scripted import ScriptedMeter


class ChunkPort(ModelPort):
    offline = True

    def __init__(self, frames: list[list[str | ToolCall | BaseException | Callable[[], None]]]) -> None:
        self.frames, self.calls = frames, 0

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        frame = self.frames[self.calls]
        self.calls += 1
        for value in frame:
            if isinstance(value, BaseException):
                raise value
            if callable(value):
                value()
                continue
            yield StreamEvent("tool_call" if isinstance(value, ToolCall) else "text", value)
        yield StreamEvent("usage", {})
        yield StreamEvent("done", {"provider": "scripted", "model": "synthetic-p4-chunks"})


class OfflineLegacy:
    def __init__(self) -> None:
        self.purged: list[tuple[str, int]] = []

    def execute(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("candidate runtime must not fall back to legacy")

    def purge(self, ident: str, epoch: int) -> None:
        self.purged.append((ident, epoch))


@pytest.fixture
def stream_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("candidate stream tests forbid physical provider HTTP or subprocesses")

    monkeypatch.setattr(httpx.Client, "send", blocked)
    monkeypatch.setattr(httpx.AsyncClient, "send", blocked)
    monkeypatch.setattr("subprocess.run", blocked)
    for name in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    previous = get_clock()
    set_clock(FrozenClock(previous.now()))
    try:
        yield p2_repo
    finally:
        set_clock(previous)


def core(
    repo: PostgresRepository,
    port: ChunkPort,
    *,
    enabled: bool = True,
    critic: ChunkPort | None = None,
) -> ConsultationService:
    agent = AgentRuntime(repo, port, ScriptedMeter(), critic=critic, offline=True, streaming_candidate=enabled)
    return ConsultationService(
        repo, model=SimpleNamespace(model="synthetic"), runtime=OfflineLegacy(), agent_runtime=agent
    )


def submit(service: ConsultationService, owner: str = "alice") -> dict[str, Any]:
    repo = service.repo
    repo.ensure_owner(owner)
    with repo.transaction(owner) as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=settings||%s WHERE id=%s").format(repo.table("core_owners")),
            (Jsonb({"runtime": "v4"}), owner),
        )
    return service.submit(owner=owner, request_id=uuid.uuid4().hex, message="合成流式问题")


def deltas(repo: PostgresRepository, run: dict[str, Any]) -> list[str]:
    with repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL("SELECT payload FROM {} WHERE owner=%s AND run_id=%s AND kind='text_delta' ORDER BY seq").format(
                repo.table("core_run_events")
            ),
            (run["owner"], run["id"]),
        ).fetchall()
    return [row["payload"]["text"] for row in rows]


@pytest.mark.parametrize("owner", ["alice", "合成用户🌙"])
def test_runtime_uses_original_forty_character_kernel_and_final_flush(
    stream_repo: PostgresRepository,
    owner: str,
) -> None:
    repo, port = stream_repo, ChunkPort([["甲" * 39, "乙", "尾"]])
    service = core(repo, port)
    run = submit(service, owner)
    result = service.execute(owner, run["id"])
    assert result["text"] == "甲" * 39 + "乙尾" and port.calls == 1
    assert deltas(repo, run) == ["甲" * 39 + "乙", "尾"]
    metadata = repo.fetch_run(owner, run["id"])["usage"][STATE_KEY]
    assert metadata["generation"] == 1 and metadata["received"] == metadata["emitted"] == 41
    assert metadata["closed"] is True and metadata["seq"] == 1
    assert service.execute(owner, run["id"]) == result and port.calls == 1
    assert repo.fetch_run(owner, run["id"])["usage"][STATE_KEY] == metadata
    with repo.transaction(owner) as connection:
        ledger = connection.execute(
            sql.SQL(
                "SELECT operation_id,result_id FROM {} WHERE owner=%s AND kind='run_event_v1' ORDER BY result_id"
            ).format(repo.table("core_operations")),
            (owner,),
        ).fetchall()
    assert any(":stream:s1:g1:chars:0:40" in row["operation_id"] for row in ledger)
    assert any(":stream:s1:g1:chars:40:41" in row["operation_id"] for row in ledger)


def test_default_off_path_keeps_original_fragment_events(stream_repo: PostgresRepository) -> None:
    repo, port = stream_repo, ChunkPort([["短", "片"]])
    service = core(repo, port, enabled=False)
    run = submit(service)
    assert service.execute("alice", run["id"])["text"] == "短片"
    assert deltas(repo, run) == ["短", "片"] and STATE_KEY not in repo.fetch_run("alice", run["id"])["usage"]


def test_next_actual_model_step_gets_new_durable_generation(stream_repo: PostgresRepository) -> None:
    repo = stream_repo
    port = ChunkPort([["先查时间", ToolCall("time", "time_context", {})], ["合成终稿"]])
    service = core(repo, port)
    run = submit(service)
    assert service.execute("alice", run["id"])["text"] == "合成终稿" and port.calls == 2
    assert deltas(repo, run) == ["先查时间", "合成终稿"]
    metadata = repo.fetch_run("alice", run["id"])["usage"][STATE_KEY]
    assert metadata["generation"] == 2 and metadata["seq"] == 3 and metadata["closed"] is True


def test_critic_and_revision_draft_never_enter_candidate_public_deltas(stream_repo: PostgresRepository) -> None:
    repo = stream_repo
    port = ChunkPort([["你一定成功"], ["这只是一个可能性"]])
    verdict = {
        "verdict": "revise",
        "issues": [{"type": "fatalism", "quote": "一定成功", "severity": 4, "fix_hint": "合成私人评审说明"}],
    }
    critic = ChunkPort([[json.dumps(verdict, ensure_ascii=False)]])
    service = core(repo, port, critic=critic)
    run = submit(service)
    result = service.execute("alice", run["id"])
    assert result["text"] == "这只是一个可能性" and result["review"]["state"] == "revised"
    assert port.calls == 2 and critic.calls == 1 and deltas(repo, run) == ["你一定成功"]
    assert repo.fetch_run("alice", run["id"])["usage"][STATE_KEY]["generation"] == 1
    with repo.transaction("alice") as connection:
        payloads = connection.execute(
            sql.SQL("SELECT kind,payload FROM {} WHERE owner=%s AND run_id=%s ORDER BY seq").format(
                repo.table("core_run_events")
            ),
            ("alice", run["id"]),
        ).fetchall()
    assert "合成私人评审说明" not in json.dumps(payloads, ensure_ascii=False)
    resets = [row["payload"] for row in payloads if row["kind"] == "text_reset"]
    assert len(resets) == 1 and resets[0]["reason"] == "revised" and resets[0]["text"] == result["text"]


def test_unfinished_generation_reclaim_refuses_new_model_or_duplicate_text(stream_repo: PostgresRepository) -> None:
    repo = stream_repo
    port = ChunkPort([["未完合成片", SystemExit("synthetic stream crash")], ["不应重新调用"]])
    service = core(repo, port)
    run = submit(service)
    with pytest.raises(SystemExit, match="synthetic stream crash"):
        service.execute("alice", run["id"])
    before = repo.fetch_run("alice", run["id"])["usage"][STATE_KEY]
    assert before["closed"] is False and deltas(repo, run) == []
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            ("alice", run["id"]),
        )
    with pytest.raises(CoreError):
        service.execute("alice", run["id"])
    assert port.calls == 1 and deltas(repo, run) == []
    assert repo.fetch_run("alice", run["id"])["usage"][STATE_KEY] == before


def test_missing_actual_request_ledger_blocks_before_physical_scripted_model(
    stream_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, port = stream_repo, ChunkPort([["不应生成"]])
    service = core(repo, port)
    monkeypatch.setattr(service.runtime_assembly.agent.ledger, "reserve", lambda *args, **kwargs: None)
    run = submit(service)
    with pytest.raises(CoreError):
        service.execute("alice", run["id"])
    assert port.calls == 0 and deltas(repo, run) == []
    assert STATE_KEY not in repo.fetch_run("alice", run["id"])["usage"]


@pytest.mark.parametrize("change", ["lease", "revoke"])
def test_old_emitter_cannot_flush_pending_text_after_real_fence_change(
    stream_repo: PostgresRepository,
    change: str,
) -> None:
    repo = stream_repo
    port = ChunkPort([])
    service = core(repo, port)
    run = submit(service)

    def fence() -> None:
        if change == "revoke":
            repo.invalidate_derived("alice", [], [run["request"]["source_message_id"]])
        else:
            with repo.transaction("alice") as connection:
                connection.execute(
                    sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE owner=%s AND id=%s").format(
                        repo.table("core_runs")
                    ),
                    ("alice", run["id"]),
                )
            repo.claim_run("alice", run["id"])

    port.frames = [["未发合成片", fence, "不应发出的合成片"]]
    with pytest.raises(CoreError):
        service.execute("alice", run["id"])
    assert port.calls == 1 and deltas(repo, run) == []
    assert repo.fetch_run("alice", run["id"])["result"] is None


@pytest.mark.parametrize("value", [1, "true", None])
def test_candidate_flag_cannot_be_coerced_to_true(stream_repo: PostgresRepository, value: Any) -> None:
    port = ChunkPort([])
    with pytest.raises(EvidenceError, match="受信程序集"):
        AgentRuntime(stream_repo, port, ScriptedMeter(), offline=True, streaming_candidate=value)
    assert port.calls == 0

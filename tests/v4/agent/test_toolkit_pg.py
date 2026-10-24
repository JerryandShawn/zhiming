"""Seven tools execute real application services inside isolated PostgreSQL schemas."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.agent.journal import Journal
from mingjing_core.agent.toolkit import ToolContext, ToolRegistry, ToolResult
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.agent_tools_contracts import DateResolution
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock

SAID_AT = datetime.fromisoformat("2026-10-17T10:30:00+08:00")


@pytest.fixture
def tool_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("工具集成测试禁止HTTP")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    for name in list(os.environ):
        if any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    return p2_repo


@dataclass
class Harness:
    repo: PostgresRepository
    service: AgentToolsService
    registry: ToolRegistry
    journal: Journal
    run: dict[str, Any]
    source: dict[str, Any]

    def finish(self) -> dict[str, Any]:
        """End only this component's leased run; no dialogue was finalized."""
        terminal = self.repo.fail_run(
            self.run["owner"],
            self.run["id"],
            "合成组件检查已结束，未生成对话",
            self.run["lease_token"],
            status="cancelled",
        )
        assert terminal["status"] == "cancelled" and terminal["lease_token"] is None
        return terminal

    def call(self, name: str, args: dict[str, Any], **flags: Any) -> tuple[ToolResult, ToolContext]:
        step = self.journal.next_or_replay(
            self.run,
            kind="tool",
            name=name,
            input_fp=self.registry.fingerprint(name, args),
        )
        ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(self.source["id"],), **flags)
        return self.registry.execute(name, args, ctx), ctx

    def write(self, kind: str = "goal", **changes: Any) -> tuple[ToolResult, ToolContext, dict[str, Any]]:
        args = {
            "message_id": self.source["id"],
            "quote": self.source["content"],
            "summary": "合成摘要",
            "kind": kind,
            **changes,
        }
        result, ctx = self.call("memory_write", args)
        return result, ctx, args


def setup(
    repo: PostgresRepository,
    text: str,
    *,
    role: str = "user",
    parser: Any = None,
    claim: bool = True,
    channel: str = "web",
    external_id: str | None = None,
) -> Harness:
    memory = MemoryService(repo)
    if channel == "feishu":
        ThreadService(repo).create("alice", request_id="synthetic-tool-channel-life")
    source = memory.receive(
        "alice",
        content=text,
        source_id=uuid.uuid4().hex,
        role=role,
        at=SAID_AT,
        channel=channel,
        external_id=external_id,
    )
    run = repo.queue_run("alice", uuid.uuid4().hex, {"message": text, "source_message_id": source["id"]})
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id='life:self' WHERE id=%s").format(repo.table("core_runs")),
            (run["id"],),
        )
    run = repo.claim_run("alice", run["id"], lease_seconds=3600) if claim else repo.fetch_run("alice", run["id"])
    service = AgentToolsService(repo, relative_parser=parser, clock=FrozenClock(SAID_AT))
    return Harness(repo, service, ToolRegistry(service), Journal(repo, "alice"), run, source)


class Parser:
    def __init__(self, status: str = "resolved") -> None:
        self.calls: list[tuple[datetime, str]] = []
        self.status = status

    def resolve(self, text: str, *, said_at: datetime, timezone: str) -> DateResolution:
        self.calls.append((said_at, timezone))
        if self.status == "resolved":
            return DateResolution("resolved", "2026-10-21", "下周三")
        return DateResolution(self.status)


def test_default_v4_goal_preserves_v3_consent_and_replays_without_revision(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我计划明年完成考研目标")
    assert (
        MemoryService(tool_repo).save_fact("alice", "self", h.source["id"], h.source["content"], "goal")["write_status"]
        == "pending_confirmation"
    )
    result, ctx, args = h.write()
    assert result.ok and result.receipt["write_status"] == "saved"
    fact = tool_repo.get("alice", "fact", result.receipt["fact_id"])
    assert fact["content"] == h.source["content"] and fact["source_refs"][0]["quote"] == h.source["content"]
    revision = tool_repo.get_revision("alice")
    assert h.registry.execute("memory_write", args, ctx).receipt == result.receipt
    assert tool_repo.get_revision("alice") == revision and len(tool_repo.list("alice", "fact")) == 1
    altered = h.registry.execute("memory_write", dict(args, summary="另一个摘要"), ctx)
    assert not altered.ok and tool_repo.get_revision("alice") == revision
    with tool_repo.transaction("alice") as connection:
        receipts = connection.execute(
            sql.SQL("SELECT receipt FROM {}").format(tool_repo.table("core_mutation_requests"))
        ).fetchall()
    assert h.source["content"] not in json.dumps(receipts, ensure_ascii=False)
    assert tool_repo.fetch_run("alice", h.run["id"])["calls"] == 0


@pytest.mark.parametrize(
    "text,code",
    [
        ("我不喜欢夜班，别忘了记住", "saved"),
        ("不要保存，我喜欢夜班", "source_optout"),
        ("假设我下周换工作", "hypothetical"),
        ("朋友说：“我喜欢夜班”", "quoted_speech"),
        ("我的密码是合成示例", "credential"),
        ("我出生于2000年", "profile_update_required"),
    ],
)
def test_write_policy_uses_real_source_not_model_claim(
    tool_repo: PostgresRepository,
    text: str,
    code: str,
) -> None:
    h = setup(tool_repo, text)
    changes = {"quote": "我喜欢夜班"} if code == "quoted_speech" else {}
    result, _, _ = h.write(kind="preference", **changes)
    assert result.receipt.get("code", result.receipt["write_status"]) == code
    assert bool(tool_repo.list("alice", "fact")) == (code == "saved")


@pytest.mark.parametrize(
    "text,level",
    [
        ("我确诊了抑郁症", "health"),
        ("我工资是五千元", "money"),
        ("我的宗教是佛教", "identity"),
        ("我正在处理诉讼", "legal"),
        ("我妈妈出生于1970年", "third_party"),
    ],
)
def test_sensitive_current_sources_create_real_proposals_only(
    tool_repo: PostgresRepository,
    text: str,
    level: str,
) -> None:
    h = setup(tool_repo, text)
    result, _, _ = h.write(kind="background")
    assert not result.ok and result.receipt["write_status"] == "pending_confirmation"
    row = tool_repo.get("alice", "proposal", result.receipt["id"])
    assert row["sensitivity"] == level and row["source_refs"][0]["message_id"] == h.source["id"]
    assert tool_repo.list("alice", "fact") == []


@pytest.mark.parametrize("role", ["assistant", "tool", "legacy"])
def test_non_user_cannot_supply_user_facts(tool_repo: PostgresRepository, role: str) -> None:
    h = setup(tool_repo, "我喜欢合成的学习计划", role=role)
    result, _, _ = h.write()
    assert not result.ok and tool_repo.list("alice", "fact") == []


def test_context_cannot_expand_run_source_or_cross_owner(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我喜欢合成的学习计划")
    other = MemoryService(tool_repo).receive("alice", content="另一个旧来源", source_id="other", at=SAID_AT)
    result, ctx, args = h.write()
    assert result.ok
    forged = replace(ctx, source_ids=(other["id"],))
    assert not h.registry.execute("memory_write", dict(args, message_id=other["id"], quote="另一个旧来源"), forged).ok
    assert not h.registry.execute("memory_write", args, replace(ctx, owner="bob")).ok
    assert not h.registry.execute("memory_write", args, replace(ctx, thread_id="life:other")).ok


@pytest.mark.parametrize(
    "clause",
    [
        "deadline_at='2026-10-16T00:00:00+00:00'",
        "cancel_requested_at=now()",
        "status='cancelled'",
        "lease_token='changed'",
        "lease_until=now()-interval '1 second'",
        "retry_epoch=retry_epoch+1",
    ],
)
def test_stale_authority_cannot_mutate(tool_repo: PostgresRepository, clause: str) -> None:
    h = setup(tool_repo, "我喜欢合成的学习计划")
    step = h.journal.next_or_replay(h.run, kind="tool", name="memory_write", input_fp="a" * 64)
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET {} WHERE id=%s").format(tool_repo.table("core_runs"), sql.SQL(clause)),
            (h.run["id"],),
        )
    args = {"message_id": h.source["id"], "quote": h.source["content"], "summary": "摘要", "kind": "goal"}
    before = tool_repo.get_revision("alice")
    assert not h.registry.execute("memory_write", args, ctx).ok
    assert tool_repo.get_revision("alice") == before and tool_repo.list("alice", "fact") == []


def test_step_fingerprint_name_and_absence_are_checked(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "合成来源")
    result, ctx = h.call("time_context", {})
    assert result.ok
    for forged in (replace(ctx, seq=99), replace(ctx, input_fp="b" * 64), replace(ctx, name="profile_get")):
        assert not h.registry.execute(forged.name, {}, forged).ok


def test_date_parser_uses_said_at_and_preserves_event_at_on_replay(tool_repo: PostgresRepository) -> None:
    parser = Parser()
    h = setup(tool_repo, "我下周三参加合成面试", parser=parser)
    result, ctx, args = h.write(kind="event")
    assert result.ok
    fact = tool_repo.get("alice", "fact", result.receipt["fact_id"])
    assert fact["event_at"] == "2026-10-21" and fact["original_expression"] == "下周三"
    assert fact["valid_from"] == SAID_AT.isoformat() and fact["valid_to"] is None
    assert parser.calls == [(SAID_AT, "Asia/Shanghai")]
    h.service.clock = FrozenClock(datetime.fromisoformat("2026-10-20T00:30:00+08:00"))
    assert h.registry.execute("memory_write", args, ctx).receipt == result.receipt
    assert len(parser.calls) == 1
    result, _ = h.call("calendar_lookup", {"start_date": "2026-10-21"})
    assert result.data["days"][0]["events"][0]["id"] == fact["id"]


@pytest.mark.parametrize(
    "parser,changes,code",
    [
        (None, {}, "date_parser_unavailable"),
        (Parser("needs_confirmation"), {}, "date_ambiguous"),
        (Parser(), {"event_at": "2026-10-22"}, "date_conflict"),
    ],
)
def test_date_unavailable_ambiguous_or_conflicting_never_saves(
    tool_repo: PostgresRepository,
    parser: Any,
    changes: dict[str, Any],
    code: str,
) -> None:
    h = setup(tool_repo, "我下周三参加合成面试", parser=parser)
    result, _, _ = h.write(kind="event", **changes)
    assert result.receipt["write_status"] == "needs_confirmation" and result.receipt["code"] == code
    assert tool_repo.list("alice", "fact") == []


def test_offline_calendar_and_search_and_confirmed_profile(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我喜欢夜班")
    result, _ = h.call("time_context", {"date": "2026-10-10"})
    assert result.ok and result.data["day_status"]["kind"] == "adjusted_workday"
    result, _ = h.call("calendar_lookup", {"start_date": "2026-10-17", "end_date": "2026-10-18"})
    assert len(result.data["days"]) == 2 and "重阳节" in result.data["days"][1]["festivals"]
    saved, _, _ = h.write(kind="preference")
    result, _ = h.call("memory_search", {"query": "夜班", "kinds": ["fact"]})
    assert result.data["items"][0]["id"] == saved.receipt["fact_id"]
    result, _ = h.call("profile_get", {})
    assert result.ok and result.data["profile"] == {} and len(result.data["facts"]) == 1


def test_notes_are_inferred_idempotent_and_forget_revokes_lineage(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我喜欢夜班")
    fact, write_ctx, write_args = h.write(kind="preference")
    args = {"summary": "合成推断", "source_ids": [h.source["id"]]}
    note, ctx = h.call("note_write", args)
    assert note.ok
    row = tool_repo.get("alice", "note", note.receipt["id"])
    assert row["inferred"] is True and row["assertion_status"] == "derived"
    assert h.registry.execute("note_write", args, ctx).receipt == note.receipt
    h.finish()
    deletion = setup(tool_repo, "请忘记我喜欢夜班")
    result, _ = deletion.call(
        "memory_forget", {"fact_id": fact.receipt["fact_id"], "message_id": deletion.source["id"]}
    )
    assert result.ok and result.receipt["write_status"] == "deleted"
    assert tool_repo.get("alice", "note", row["id"], include_deleted=True)["status"] != "active"
    assert not h.registry.execute("memory_write", write_args, write_ctx).ok
    assert not h.registry.execute("note_write", args, ctx).ok
    with pytest.raises(EvidenceError, match="Withdrawn source range"):
        MemoryService(tool_repo).save_fact("alice", "self", h.source["id"], h.source["content"], "preference")


def test_incognito_and_crisis_cannot_write(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我喜欢夜班")
    for flags in ({"incognito": True}, {"crisis": True}):
        result, _ = h.call("note_write", {"summary": "合成推断", "source_ids": [h.source["id"]]}, **flags)
        assert not result.ok
    assert tool_repo.list("alice", "note") == []


def test_profile_reads_only_confirmed_fields(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "请记住我的名字是合成甲")
    memory = MemoryService(tool_repo)
    row = memory.save_fact(
        "alice",
        "self",
        h.source["id"],
        h.source["content"],
        "profile",
        field="name",
        value="合成甲",
    )
    assert row["write_status"] == "saved"
    result, _ = h.call("profile_get", {})
    assert result.data["profile"] == {"name": "合成甲"}
    assert result.data["facts"][0]["source_refs"][0]["quote"] == h.source["content"]


def test_withdrawn_span_and_incorrect_quote_never_write(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我喜欢夜班")
    bad, _, _ = h.write(quote="我喜欢白班")
    assert not bad.ok and tool_repo.list("alice", "fact") == []
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(
            connection,
            "alice",
            "source_span",
            "synthetic-span",
            "stopped",
            {"message_id": h.source["id"], "start": 0, "end": len(h.source["content"])},
        )
    before = tool_repo.get_revision("alice")
    result, _, _ = h.write(kind="preference")
    assert not result.ok and tool_repo.get_revision("alice") == before


def test_note_cannot_smuggle_credentials_or_ignore_optout(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "不要保存我喜欢夜班")
    result, _ = h.call("note_write", {"summary": "合成推断", "source_ids": [h.source["id"]]})
    assert result.receipt["write_status"] == "stopped"
    h.finish()
    h = setup(tool_repo, "我喜欢夜班")
    result, _ = h.call("note_write", {"summary": "sk-" + "synthetic" * 4, "source_ids": [h.source["id"]]})
    assert result.receipt["code"] == "credential"
    result, _, _ = h.write(summary="我的密码是合成示例")
    assert result.receipt["code"] == "credential"
    assert tool_repo.list("alice", "note") == [] and tool_repo.list("alice", "fact") == []


def test_event_date_filter_uses_event_at_not_created_or_valid_from(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我下周三参加合成面试", parser=Parser())
    result, _, _ = h.write(kind="event")
    assert result.ok
    found, _ = h.call("memory_search", {"query": "面试", "since": "2026-10-21", "until": "2026-10-21"})
    assert len(found.data["items"]) == 1
    absent, _ = h.call("memory_search", {"query": "面试", "until": "2026-10-17"})
    assert absent.data["items"] == []

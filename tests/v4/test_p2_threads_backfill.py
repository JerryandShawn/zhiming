"""Life history, successful replies and migration replay use real PostgreSQL."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from mingjing_core.adapters.web import create_app
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.memory.backfill import backfill
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tests.test_core_pg_channels import FixtureModel
from tools.eval.targets.v3_target import V3Target


def test_thread_latest_thirty_keeps_roles_channels_dates_and_owner_isolation(p2_repo):
    memory = MemoryService(p2_repo)
    base = datetime(2026, 10, 1, tzinfo=UTC)
    for index in range(40):
        memory.receive(
            "alice",
            content=f"第{index}条合成历史",
            source_id=str(index),
            conversation_id=f"topic-{index % 2}",
            at=base + timedelta(minutes=index),
            channel="synthetic",
        )
    reply = memory.record_assistant_message(
        "alice",
        "self",
        "life:self",
        "方案 B 是先内部转岗",
        run_id="old-run",
        channel="feishu",
        at=base + timedelta(minutes=40),
    )
    memory.receive("bob", content="不属于 alice 的历史", source_id="other", at=base + timedelta(minutes=41))
    snapshot = memory.snapshot("alice", conversation_id="new-topic")
    assert len(snapshot["history"]) == 30
    assert snapshot["history"][0]["content"] == "第11条合成历史"
    assert snapshot["history"][-1]["id"] == reply["id"]
    assert snapshot["history"][-1]["channel"] == "feishu"
    assert all(row["thread_id"] == "life:self" for row in snapshot["history"])
    assert all(row["owner"] == "alice" for row in snapshot["history"])


@pytest.mark.parametrize("assertion", ["user_asserted", "legacy_unverified"])
def test_assistant_can_never_be_saved_as_a_user_fact_even_with_legacy_flag(p2_repo, assertion):
    memory = MemoryService(p2_repo)
    message = memory.record_assistant_message(
        "alice", "self", "life:self", "请记住，我喜欢散步", run_id="assistant", channel="web"
    )
    with pytest.raises(EvidenceError, match="Assistant"):
        memory.save_fact("alice", "self", message["id"], "我喜欢散步", assertion_status=assertion)


def test_assistant_revision_replay_and_source_withdrawal_never_restore_text(p2_repo):
    memory = MemoryService(p2_repo)
    original = memory.receive("alice", content="请记住，我不能上夜班", source_id="source")
    fact = memory.save_fact("alice", "self", original["id"], "我不能上夜班", "constraint")
    kwargs = {"run_id": "reply", "channel": "web", "source_ids": [original["id"]], "used_fact_ids": [fact["id"]]}
    reply = memory.record_assistant_message("alice", "self", "life:self", "方案 B 排除夜班", **kwargs)
    assert memory.record_assistant_message("alice", "self", "life:self", "方案 B 排除夜班", **kwargs)["revision"] == 1
    revised = memory.record_assistant_message("alice", "self", "life:self", "方案 B 先核实白班", **kwargs)
    assert revised["id"] == reply["id"] and revised["revision"] == 2
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    redacted = p2_repo.get("alice", "message", reply["id"])
    assert redacted["content"] == "〔已删除的内容〕" and redacted["redacted"]
    assert p2_repo.search("alice", "self", ["白班"], ["message"], 10) == []
    with pytest.raises(EvidenceError, match="Withdrawn"):
        memory.record_assistant_message("alice", "self", "life:self", "方案 B 先核实白班", **kwargs)


def test_partial_source_withdrawal_removes_search_vector_and_derived_note(p2_repo):
    memory = MemoryService(p2_repo)
    source = memory.receive("alice", content="我不吃辣。我的计划是考研", source_id="partial")
    fact = memory.save_fact("alice", "self", source["id"], "我不吃辣", "preference")
    p2_repo.put(
        "alice", "note", "derived", {"content": "不吃辣的安排", "source_ids": [source["id"]]}, expected_revision=0
    )
    with p2_repo.transaction() as connection:
        connection.execute(
            sql.SQL("INSERT INTO {} VALUES('alice','message',%s,0,'synthetic',ARRAY[1.0]::real[],'fp')").format(
                p2_repo.table("core_embeddings")
            ),
            (source["id"],),
        )
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    assert p2_repo.search("alice", "self", ["辣"], ["message"], 10) == []
    remaining = p2_repo.search("alice", "self", ["考研"], ["message"], 10)
    assert len(remaining) == 1 and "不吃辣" not in remaining[0]["content"]
    assert p2_repo.get("alice", "note", "derived", include_deleted=True)["status"] == "deleted"
    with p2_repo.transaction() as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT count(*) AS count FROM {}").format(p2_repo.table("core_embeddings"))
            ).fetchone()["count"]
            == 0
        )
    backfill(memory, "alice", apply=True)
    assert p2_repo.search("alice", "self", ["辣"], ["message"], 10) == []
    original = p2_repo.get("alice", "message", source["id"])
    p2_repo.update("alice", "message", source["id"], {"case_ids": []}, expected_revision=original["revision"])
    assert p2_repo.search("alice", "self", ["辣"], ["message"], 10) == []


def seed_historical_runs(repo, count):
    memory = MemoryService(repo)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with repo.transaction("alice") as connection:
        for index in range(count):
            operation = f"historical:{index}"
            at = start + timedelta(minutes=index)
            source = memory.receive(
                "alice", content=f"合成历史轮次{index}", source_id=operation, conversation_id="old-topic", at=at
            )
            request = {
                "message": source["content"],
                "source_message_id": source["id"],
                "mode": "chat",
                "case_ids": [],
                "conversation_id": "old-topic",
                "selection": {},
            }
            run = repo.begin_run("alice", operation, request)
            versions = {"message:" + source["id"]: source["revision"]}
            repo.set_run_dependencies("alice", run["id"], versions, run["lease_token"])
            result = {
                "schema_version": "core3.0",
                "validation": {"status": "validated"},
                "answer": f"合成历史回答{index}",
                "cited_fact_ids": [],
                "cited_claim_ids": [],
            }
            repo.commit_run("alice", run["id"], versions, result, run["lease_token"])
            connection.execute(
                sql.SQL("UPDATE {} SET created_at=%s,updated_at=%s WHERE id=%s").format(repo.table("core_runs")),
                (at, at + timedelta(seconds=30), run["id"]),
            )
        connection.execute(
            sql.SQL(
                "UPDATE {} SET data=data-ARRAY['thread_id','at_ms','origin_conversation_id','search_tokens'] "
                "WHERE owner='alice' AND kind='message'"
            ).format(repo.table("core_entities"))
        )
    return memory


def test_backfill_three_hundred_rounds_dry_run_apply_and_repeat(p2_repo):
    memory = seed_historical_runs(p2_repo, 300)
    before = [(row["id"], row["revision"], row["content"]) for row in p2_repo.list("alice", "message")]
    dry = backfill(memory, "alice")
    assert dry["message_metadata"] == dry["search_tokens"] == dry["assistant_created"] == 300
    assert len(p2_repo.list("alice", "message")) == 300
    assert all("thread_id" not in row for row in p2_repo.list("alice", "message"))
    assert backfill(memory, "alice", apply=True)["assistant_created"] == 300
    repeated = backfill(memory, "alice", apply=True)
    assert repeated["assistant_created"] == repeated["message_metadata"] == repeated["search_tokens"] == 0
    assert repeated["assistant_existing"] == 300
    users = [row for row in p2_repo.list("alice", "message") if row["role"] == "user"]
    assert [(row["id"], row["revision"], row["content"]) for row in users] == before
    assert len(p2_repo.list("alice", "message")) == 600
    assert not p2_repo.list("alice", "fact")
    assert all(row["origin_conversation_id"] == "old-topic" for row in p2_repo.list("alice", "message"))


def test_interrupted_backfill_rolls_back_and_can_resume_without_duplicates(p2_repo, monkeypatch):
    memory = seed_historical_runs(p2_repo, 12)
    import mingjing_core.memory.backfill as module

    real = module.record_assistant
    calls = []

    def interrupted(*args, **kwargs):
        calls.append(kwargs["run_id"])
        if len(calls) == 5:
            raise RuntimeError("synthetic interruption")
        return real(*args, **kwargs)

    monkeypatch.setattr(module, "record_assistant", interrupted)
    with pytest.raises(RuntimeError, match="synthetic"):
        backfill(memory, "alice", apply=True)
    assert len(p2_repo.list("alice", "message")) == 12
    assert all("thread_id" not in row for row in p2_repo.list("alice", "message"))
    monkeypatch.setattr(module, "record_assistant", real)
    assert backfill(memory, "alice", apply=True)["assistant_created"] == 12
    assert backfill(memory, "alice", apply=True)["assistant_created"] == 0


def test_backfill_skips_withdrawn_sources_and_deleted_runs(p2_repo):
    memory = seed_historical_runs(p2_repo, 3)
    sources = p2_repo.list("alice", "message")
    with p2_repo.transaction("alice") as connection:
        p2_repo.revoke(connection, "alice", "message", sources[0]["id"], "deleted")
        connection.execute(
            sql.SQL("UPDATE {} SET result=NULL,status='revoked' WHERE request->>'source_message_id'=%s").format(
                p2_repo.table("core_runs")
            ),
            (sources[1]["id"],),
        )
    result = backfill(memory, "alice", apply=True)
    assert result["assistant_created"] == 1 and result["assistant_skipped"] == 1
    assert len([row for row in p2_repo.list("alice", "message") if row["role"] == "assistant"]) == 1


def test_service_payload_cross_topic_and_api_history_do_not_duplicate_reply(p2_repo, monkeypatch):
    original_clock = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat("2026-10-17T10:30:00+08:00")))
    provider = FixtureModel()
    target = V3Target(dsn=p2_repo.dsn, provider=provider)
    monkeypatch.setenv("MINGJING_TOKEN", "p2-synthetic-only")
    monkeypatch.setenv("MINGJING_OWNER_ID", target.owner)
    try:
        target.reset({"profile": "empty_profile"})
        first = target.send({"user": "给三个方案", "conversation_id": "old-topic", "_index": 1})
        assert first.error is None
        second = target.send({"user": "第二个方案继续", "conversation_id": "new-topic", "_index": 2})
        assert second.error is None
        history = provider.requests[2]["payload"]["reference_data"]["recent_history"]
        assert any(row["role"] == "assistant" and row["content"] == first.text for row in history)
        assert all(set(row) == {"role", "at", "channel", "content"} for row in history)
        assert "2026年10月17日" in provider.requests[2]["payload"]["reference_data"]["now"]
        client = TestClient(create_app(target.service))
        rows = client.get("/api/history", headers={"X-Token": "p2-synthetic-only"}).json()
        assert len([row for row in rows if row["role"] == "assistant"]) == 2
        assert all("cursor" in row for row in rows)
    finally:
        target.close()
        set_clock(original_clock)

"""Reader compatibility uses real PG, finalization, outbox and local HTTP."""

from __future__ import annotations

import asyncio
import copy
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.channels.hermes import render_channel
from mingjing_core.adapters.channels.reports import CoreReportAdapter
from mingjing_core.adapters.delivery import OutboxService
from mingjing_core.adapters.tarot import TarotService
from mingjing_core.adapters.web import create_app
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.memory.history import history_window
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock

from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, cycle, modify, prepare


@pytest.fixture
def reader_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    def reject(*args, **kwargs):
        raise AssertionError("读取端测试禁止真实HTTP")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject)
    old = get_clock()
    set_clock(FrozenClock(datetime(2026, 10, 18, 12, tzinfo=UTC)))
    try:
        yield p2_repo
    finally:
        set_clock(old)


def completed(repo: PostgresRepository, *, tarot: tuple[str, str] | None = None) -> tuple[dict, dict]:
    run, registry, frozen = prepare(repo, "请核对合成安排")
    if tarot:
        request = dict(run["request"], draw_id=tarot[0], reading_id=tarot[1])
        with repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET request=%s WHERE id=%s").format(repo.table("core_runs")),
                (Jsonb(request), run["id"]),
            )
        run = repo.fetch_run("alice", run["id"])
    outcome = cycle(ScriptedPort([answer("已核对合成安排")]), registry, run, frozen).execute()
    result = AgentFinalizer(repo).finalize(
        run,
        text=outcome.text,
        alias_map=outcome.alias_map,
        versions=outcome.versions,
        snapshot_revision=frozen.snapshot_revision,
        usage=outcome.usage,
    )
    return repo.fetch_run("alice", run["id"]), result


def test_core4_outbox_uses_run_dependencies_and_rechecks_them(reader_repo: PostgresRepository) -> None:
    repo = reader_repo
    repo.bind_channel("alice", "feishu", "ou_synthetic")
    run, result = completed(repo)
    assert "dependencies" not in result["meta"]["core_run"]
    outbox = OutboxService(repo)
    item = outbox.prepare_delivery(
        owner="alice", run_id=run["id"], business_id="reader-fixture", channel="feishu", target="ou_synthetic"
    )
    claim = outbox.claim_delivery(owner="alice", outbox_id=item["id"])
    assert claim["dependencies"] == run["dependencies"]
    assert claim["payload"] == result and render_channel(claim["payload"]) == result["text"]
    outbox.record_delivery(owner="alice", outbox_id=item["id"], status="rejected", claim_token=claim["claim_token"])
    source = repo.get("alice", "message", run["request"]["source_message_id"])
    repo.update("alice", "message", source["id"], {"content": "已更正合成原话"}, expected_revision=source["revision"])
    with pytest.raises(RevisionConflict):
        outbox.claim_delivery(owner="alice", outbox_id=item["id"])
    assert outbox.status("alice")["rows"][0]["status"] == "stale"


def test_core4_outbox_rejects_envelope_from_another_run(reader_repo: PostgresRepository) -> None:
    run, result = completed(reader_repo)
    forged = dict(run, result=copy.deepcopy(result))
    forged["result"]["meta"]["core_run"]["run_id"] = "forged-run"
    with pytest.raises(EvidenceError):
        OutboxService(reader_repo)._fresh("alice", forged)


def test_core4_tarot_keeps_persisted_link_and_execution_versions(reader_repo: PostgresRepository) -> None:
    repo, cards = reader_repo, TarotService(reader_repo)
    case = MemoryService(repo).create_case("alice", "self", "合成事项", operation_id="reading-case")
    draw = cards.create_draw(
        "alice", subject_id="self", case_id=case["id"], question="合成反思", idempotency_key="reader-draw"
    )["draw"]
    cards.reveal("alice", draw["id"])
    reading = cards.begin_reading(
        "alice", draw["id"], model="scripted", prompt_version="core4.0", context_snapshot={}, idempotency_key="read"
    )["reading"]
    run, result = completed(repo, tarot=(draw["id"], reading["id"]))
    with pytest.raises(EvidenceError):
        cards.finish_reading(
            "alice", reading["id"], result=dict(result, answer="伪造"), validation=result["validation"]
        )
    saved = cards.finish_reading("alice", reading["id"], result=result, validation={"valid": False})
    assert saved["status"] == "success" and saved["result"] == result
    assert saved["validation"] == result["validation"]
    assert saved["execution_snapshot"]["dependencies"] == run["dependencies"]
    assert cards.finish_reading("alice", reading["id"], result=result, validation={}) == saved


def test_core4_history_stored_and_fallback_are_the_same_validated_body(reader_repo: PostgresRepository) -> None:
    repo = reader_repo
    run, result = completed(repo)
    before = history_window(repo, "alice", "self", "shared", 60, None, "")
    assistant = [row for row in before if row["role"] == "assistant"]
    assert len(assistant) == 1 and assistant[0]["content"] == result["text"]
    assert assistant[0]["meta"] == result
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner=%s AND kind='message' AND data->>'run_id'=%s").format(
                repo.table("core_entities")
            ),
            ("alice", run["id"]),
        )
    fallback = history_window(repo, "alice", "self", "shared", 60, None, "")
    assistant = [row for row in fallback if row["role"] == "assistant"]
    assert len(assistant) == 1 and assistant[0]["content"] == result["text"]
    assert assistant[0]["meta"] == result
    assert history_window(repo, "bob", "self", "shared", 60, None, "") == []


def test_web_result_run_and_history_read_core4_without_invoking_a_model(
    reader_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, memory = reader_repo, MemoryService(reader_repo)
    run, result = completed(repo)
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-read-token")
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", "{}")
    service = SimpleNamespace(repo=repo, memory=memory)
    headers = {"X-Token": "synthetic-read-token"}
    client = TestClient(create_app(service))
    chat = client.get("/api/chat/" + run["id"], headers=headers)
    assert chat.status_code == 200 and chat.json()["answer"] == result["text"]
    assert chat.json()["meta"] == result
    assert client.get("/api/runs/" + run["id"], headers=headers).json()["result"] == result
    rows = client.get("/api/history", headers=headers).json()
    assert [row["meta"] for row in rows if row["role"] == "assistant"] == [result]
    assert client.get("/api/chat/" + run["id"]).status_code == 401


def test_feishu_core4_history_uses_recorded_reply_and_no_transport(
    reader_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, memory = reader_repo, MemoryService(reader_repo)
    repo.bind_channel("alice", "feishu", "ou_synthetic")
    source = memory.receive(
        "alice", content="合成飞书原话", source_id=uuid.uuid4().hex, channel="feishu", external_id="ou_synthetic"
    )
    run = repo.queue_run(
        "alice", uuid.uuid4().hex, {"message": source["content"], "source_message_id": source["id"], "case_ids": []}
    )
    modify(repo, run, "runtime='v4',thread_id='life:self'")
    run = repo.claim_run("alice", run["id"], lease_seconds=150)
    port = ScriptedPort([answer("合成飞书已核对")])
    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
    )
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-read-token")
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", "{}")
    client = TestClient(create_app(SimpleNamespace(repo=repo, memory=memory)))
    response = client.get("/api/feishu_history", headers={"X-Token": "synthetic-read-token"})
    assert response.status_code == 200
    replies = [row for row in response.json() if row["role"] == "assistant"]
    assert len(replies) == 1 and replies[0]["content"] == result["text"]
    assert replies[0]["run_id"] == run["id"] and replies[0]["policy"]["run_context"] is False
    assert render_channel(result) == replies[0]["content"] and len(port.requests) == 1


def test_report_core4_manifest_and_delivery_do_not_read_legacy_meta_dependencies(
    reader_repo: PostgresRepository,
) -> None:
    repo = reader_repo
    repo.bind_channel("alice", "report", "synthetic-report", binding_kind="task")
    repo.bind_channel("alice", "feishu", "ou_synthetic")
    run, result = completed(repo)

    async def consult(**kwargs):
        return result

    service = SimpleNamespace(repo=repo, consult=consult, prepare_delivery=OutboxService(repo).prepare_delivery)
    adapter = CoreReportAdapter(".", service=service)
    report = asyncio.run(adapter.prepare(external_id="synthetic-report", kind="daily", day="2026-10-18"))
    manifest = repo.get("alice", "report", report["report"]["business_id"])
    assert manifest["schema_version"] == "core4.0" and manifest["content"] == result["text"]
    assert manifest["dependencies"] == run["dependencies"] and manifest["guidance"] == result
    prepared = asyncio.run(
        adapter.prepare_delivery(external_id="synthetic-report", result=report, channel="feishu", target="ou_synthetic")
    )
    assert prepared["status"] == "pending"

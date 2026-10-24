"""Real PG fixed-window aggregation preserves independent sources and never executes a model."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from mingjing_core.adapters.feishu_gateway import FeishuGateway
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.feishu_ingress import FeishuIngress
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture
from .test_thread_inbox_pg import set_runtime


@pytest.fixture(name="feishu_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    p2_repo.bind_channel("alice", "feishu", "ou_syntheticAlice")
    p2_repo.bind_channel("bob", "feishu", "ou_syntheticBob")
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def receive(
    ingress: FeishuIngress,
    ident: str,
    text: str = "合成飞书原话",
    *,
    offset: int = 0,
    owner: str = "alice",
    author: str = "ou_syntheticAlice",
    chat: str = "oc_syntheticAlice",
) -> dict[str, Any]:
    return ingress.receive(
        owner=owner,
        subject="self",
        author=author,
        chat_id=chat,
        message_id=ident,
        text=text,
        at=datetime(2026, 10, 17, 12, tzinfo=UTC) + timedelta(milliseconds=offset),
    )


def test_fixed_2500ms_window_creates_one_run_with_distinct_quote_ranges(feishu_repo: PostgresRepository) -> None:
    core = ConsultationService(feishu_repo)
    ingress = FeishuIngress(core)
    first = receive(ingress, "om_first", "  第一条\n ")
    get_clock().advance(timedelta(milliseconds=2499))
    second = receive(ingress, "om_second", "第二条补充", offset=10)
    assert first["run_id"] is second["run_id"] is None and feishu_repo.queued_runs() == []
    assert ingress.flush("alice", first["inbound_id"]) == {"status": "buffering", "run_id": None}
    get_clock().advance(timedelta(milliseconds=1))
    queued = ingress.flush("alice", second["inbound_id"])
    assert queued["status"] == "queued"
    run = feishu_repo.fetch_run("alice", queued["run_id"])
    assert run["request"]["message"] == "第二条补充" and run["request"]["source_message_ids"] != []
    sources = [feishu_repo.get("alice", "message", ident) for ident in run["request"]["source_message_ids"]]
    assert [row["content"] for row in sources] == ["  第一条\n ", "第二条补充"]
    assert sources[0]["at"] != sources[1]["at"] and run["request"]["source_message_id"] == sources[-1]["id"]
    assert run["request"]["source_segments"] == [
        dict(message_id=row["id"], version=row["revision"], start=0, end=len(row["content"])) for row in sources
    ]
    assert len(feishu_repo.queued_runs()) == 1 and run["calls"] == 0
    assert feishu_repo.get("alice", "request", first["inbound_id"])["run_id"] == run["id"]
    assert feishu_repo.get("alice", "request", first["inbound_id"])["business_id"] == "feishu:message:om_first"


def test_exact_window_boundary_starts_new_batch_and_duplicates_do_not_extend(feishu_repo: PostgresRepository) -> None:
    ingress = FeishuIngress(ConsultationService(feishu_repo))
    first = receive(ingress, "om_first")
    get_clock().advance(timedelta(milliseconds=2499))
    assert receive(ingress, "om_first")["inbound_id"] == first["inbound_id"]
    get_clock().advance(timedelta(milliseconds=1))
    second = receive(ingress, "om_second", offset=2)
    first_item = feishu_repo.get("alice", "request", first["inbound_id"])
    second_item = feishu_repo.get("alice", "request", second["inbound_id"])
    assert first_item["batch_id"] != second_item["batch_id"] and first_item["run_id"] is not None
    assert second_item["run_id"] is None and len(feishu_repo.queued_runs()) == 1


def test_restart_flushes_same_batch_once_without_clock_or_model_io(feishu_repo: PostgresRepository) -> None:
    core = ConsultationService(feishu_repo)
    first = receive(FeishuIngress(core), "om_restart")
    get_clock().advance(timedelta(milliseconds=2500))
    assert FeishuIngress(core).flush_due() == {"queued": 1, "failed": 0}
    run = feishu_repo.get("alice", "request", first["inbound_id"])["run_id"]
    assert FeishuIngress(core).flush_due() == {"queued": 0, "failed": 0}
    assert len(feishu_repo.queued_runs()) == 1 and feishu_repo.fetch_run("alice", run)["calls"] == 0


def test_different_owner_and_private_chat_never_share_a_batch(feishu_repo: PostgresRepository) -> None:
    ingress = FeishuIngress(ConsultationService(feishu_repo))
    items = [
        receive(ingress, "om_alice"),
        receive(ingress, "om_alice_other_chat", chat="oc_other"),
        receive(ingress, "om_bob", owner="bob", author="ou_syntheticBob", chat="oc_syntheticBob"),
    ]
    batches = [feishu_repo.get(item["owner"], "request", item["inbound_id"])["batch_id"] for item in items]
    assert len(set(batches)) == 3
    with pytest.raises(ScopeError):
        receive(ingress, "om_forged", owner="bob")
    get_clock().advance(timedelta(milliseconds=2500))
    assert ingress.flush_due() == {"queued": 3, "failed": 0}


@pytest.mark.parametrize("replacement", [{"text": "被替换的原话"}, {"offset": 2}, {"chat": "oc_other"}])
def test_same_native_id_cannot_replace_text_time_or_chat(
    feishu_repo: PostgresRepository, replacement: dict[str, Any]
) -> None:
    ingress = FeishuIngress(ConsultationService(feishu_repo))
    receive(ingress, "om_stable")
    with pytest.raises(EvidenceError):
        receive(ingress, "om_stable", **replacement)
    assert len(feishu_repo.list("alice", "message")) == 1


def test_gateway_only_buffers_or_queues_without_direct_consult(
    feishu_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = ConsultationService(feishu_repo)

    async def no_consult(**_: Any) -> None:
        pytest.fail("gateway must not execute consultation")

    monkeypatch.setattr(core, "consult", no_consult)
    gateway = FeishuGateway(core, lambda *_: pytest.fail("no delivery before a committed result"))
    accepted = receive(gateway.ingress, "om_queue_only")

    async def exercise() -> None:
        assert (await gateway.process("alice", accepted["inbound_id"]))["status"] == "buffering"
        get_clock().advance(timedelta(milliseconds=2500))
        assert (await gateway.process("alice", accepted["inbound_id"]))["status"] == "queued"
        assert (await gateway.tick())["failed"] == 0

    asyncio.run(exercise())
    run = feishu_repo.queued_runs("alice")[0]
    assert run["runtime"] == "v3" and run["calls"] == 0


def test_v4_merged_run_reaches_core4_and_shared_outbox_sends_once(feishu_repo: PostgresRepository) -> None:
    set_runtime(feishu_repo, "v4")
    port = ScriptedPort([answer("合成最终飞书答复")])
    core = ConsultationService(
        feishu_repo, agent_runtime=AgentRuntime(feishu_repo, port, SyntheticMeter(), offline=True)
    )
    sent = []

    def transport(*values: Any) -> str:
        sent.append(values)
        return "om_syntheticReceipt"

    gateway = FeishuGateway(core, transport)
    first = receive(gateway.ingress, "om_v4_first", "第一条合成问题")
    second = receive(gateway.ingress, "om_v4_second", "第二条合成补充", offset=1)
    get_clock().advance(timedelta(milliseconds=2500))
    queued = gateway.ingress.flush("alice", first["inbound_id"])
    run = feishu_repo.fetch_run("alice", queued["run_id"])
    assert run["runtime"] == "v4" and sent == [] and port.requests == []
    result = core.execute("alice", run["id"])
    assert result["schema"] == "core4.0"
    users = [message.content for message in port.requests[0]["messages"] if message.role == "user"]
    assert "第一条合成问题" in users and "第二条合成补充" in users

    async def deliver() -> None:
        assert (await gateway.process("alice", first["inbound_id"]))["status"] == "sent"
        assert (await gateway.process("alice", second["inbound_id"]))["status"] == "sent"
        assert (await gateway.tick())["failed"] == 0

    asyncio.run(deliver())
    assert len(sent) == 1 and sent[0][0] == "ou_syntheticAlice" and "合成最终飞书答复" in sent[0][1]

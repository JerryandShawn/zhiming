"""Channel lineage blocks even trusted callers from redirecting a v4 web reply."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.channels.delivery import CoreDeliveryWorker
from mingjing_core.adapters.delivery import DeliveryUncertain, OutboxService
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import cycle_repo as source_fixture
from .test_result_readers_pg import completed

TARGET = "ou_syntheticOrigin"


@pytest.fixture
def repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def route(run: dict, *, target: str = TARGET) -> dict:
    return dict(owner="alice", run_id=run["id"], business_id="origin:" + run["id"], channel="feishu", target=target)


def legacy_pending(repo: PostgresRepository, run: dict, result: dict) -> str:
    """Represent a pre-fix bad queue row, without using the now guarded prepare API."""
    ident = uuid.uuid4().hex
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL(
                "INSERT INTO {}(id,owner,subject,business_id,channel,target,run_id,payload,dependencies,due) "
                "VALUES(%s,'alice','self',%s,'feishu',%s,%s,%s,%s,%s)"
            ).format(repo.table("delivery_outbox")),
            (
                ident,
                "origin:" + run["id"],
                TARGET,
                run["id"],
                Jsonb(result),
                Jsonb(run["dependencies"]),
                get_clock().now(),
            ),
        )
    return ident


@pytest.mark.parametrize("phase", ["prepare", "claim"])
def test_web_reply_with_feishu_binding_cannot_be_redirected(repo: PostgresRepository, phase: str) -> None:
    repo.bind_channel("alice", "feishu", TARGET)
    ThreadService(repo).create("alice", request_id="synthetic-origin-thread")
    run, result = completed(repo)
    outbox = OutboxService(repo)
    if phase == "prepare":
        with pytest.raises(ScopeError, match="其他渠道"):
            outbox.prepare_delivery(**route(run))
        assert outbox.status("alice")["rows"] == []
    else:
        ident = legacy_pending(repo, run, result)
        sent = []

        def transport(*args):
            sent.append(args)
            return "synthetic-not-used"

        with pytest.raises(ScopeError, match="其他渠道"):
            asyncio.run(
                CoreDeliveryWorker(SimpleNamespace(claim_delivery=outbox.claim_delivery), transport).deliver(
                    owner="alice", outbox_id=ident
                )
            )
        row = outbox.status("alice")["rows"][0]
        assert row["status"] == "stale" and row["attempts"] == 0 and sent == []


@pytest.mark.parametrize("fault", ["missing_source", "request_channel", "other_target", "withdrawn", "revision"])
def test_v4_destination_uses_current_pg_originals_not_request_claims(repo: PostgresRepository, fault: str) -> None:
    repo.bind_channel("alice", "feishu", TARGET)
    repo.bind_channel("alice", "feishu", "ou_syntheticOtherOrigin")
    ThreadService(repo).create("alice", request_id="synthetic-origin-thread")
    run, _ = completed(repo, delivery_target=None if fault == "request_channel" else TARGET)
    target = "ou_syntheticOtherOrigin" if fault == "other_target" else TARGET
    source = repo.get("alice", "message", run["request"]["source_message_id"])
    with repo.transaction("alice") as connection:
        if fault in {"missing_source", "request_channel"}:
            request = dict(
                run["request"],
                **({"source_message_id": "missing"} if fault == "missing_source" else {"channel": "feishu"}),
            )
            connection.execute(
                sql.SQL("UPDATE {} SET request=%s WHERE owner='alice' AND id=%s").format(repo.table("core_runs")),
                (Jsonb(request), run["id"]),
            )
        elif fault == "withdrawn":
            repo.revoke(connection, "alice", "message", source["id"], "deleted")
        elif fault == "revision":
            repo.update("alice", "message", source["id"], {"content": "合成更正"}, expected_revision=source["revision"])
    outbox = OutboxService(repo)
    with pytest.raises((EvidenceError, RevisionConflict, ScopeError)):
        outbox.prepare_delivery(**route(run, target=target))
    assert outbox.status("alice")["rows"] == []


def test_v4_scheduled_mode_without_real_report_manifest_is_not_an_escape(repo: PostgresRepository) -> None:
    repo.bind_channel("alice", "feishu", TARGET)
    run, _ = completed(repo, mode="scheduled_report")
    with pytest.raises(EvidenceError, match="发布记录"):
        OutboxService(repo).prepare_delivery(**route(run))


def test_native_feishu_unknown_delivery_still_never_retries(repo: PostgresRepository) -> None:
    repo.bind_channel("alice", "feishu", TARGET)
    run, _ = completed(repo, delivery_target=TARGET)
    outbox, sent = OutboxService(repo), []
    item = outbox.prepare_delivery(**route(run))

    def transport(*args):
        sent.append(args)
        raise TimeoutError("synthetic ambiguous local receipt")

    service = SimpleNamespace(claim_delivery=outbox.claim_delivery, record_delivery=outbox.record_delivery)
    receipt = asyncio.run(CoreDeliveryWorker(service, transport).deliver(owner="alice", outbox_id=item["id"]))
    assert receipt["status"] == "uncertain" and len(sent) == 1
    with pytest.raises(DeliveryUncertain):
        outbox.claim_delivery(owner="alice", outbox_id=item["id"])
    assert len(sent) == 1

"""Native PG lease, version, replay and withdrawal fences for P8 documents."""

from copy import deepcopy
from dataclasses import replace

import pytest

from mingjing_core.adapters.charts.tool_evidence import evidence_result
from mingjing_core.application.agent_tools_charts import prepare_chart
from mingjing_core.application.charts_documents import persist_documents, verify_p8_document
from mingjing_core.domain.contracts import CoreError, EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_computation_charts_pg import context, profile
from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as source_fixture


@pytest.fixture(name="repo")
def repository(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_fixture.__wrapped__(p2_repo, monkeypatch)


def prepared(repo: PostgresRepository):
    facts = profile(repo)
    h = setup(repo, "看看合成八字")
    _, ctx = context(h)
    snapshot = prepare_chart(h.service, ctx)
    scope = {
        "owner_user_id": ctx.owner,
        "subject_id": ctx.subject,
        "revision": snapshot["revision"],
        "operation_id": ctx.operation_id,
    }
    payload = evidence_result("p8-daily-transit-v1", {"value": 1}, [], [], scope)
    doc = verify_p8_document(
        payload,
        kind="daily_transit",
        owner=ctx.owner,
        subject=ctx.subject,
        revision=snapshot["revision"],
        operation_id=ctx.operation_id,
        source_sha256={"synthetic-worker.py": "a" * 64},
    )
    return h, ctx, snapshot, doc, facts


def test_p8_persistence_replays_real_artifact_once_and_refuses_withdrawal(repo: PostgresRepository) -> None:
    h, ctx, snapshot, doc, _ = prepared(repo)
    rows = persist_documents(h.service, ctx, snapshot, [doc])
    assert persist_documents(h.service, ctx, snapshot, [doc]) == rows
    assert len(repo.list("alice", "artifact")) == 1
    row = repo.get("alice", "artifact", rows[0]["id"])
    assert row["p8_document"] == doc and row["source_versions"] == snapshot["versions"]
    repo.delete("alice", "artifact", row["id"], expected_revision=row["revision"])
    with pytest.raises(CoreError):
        persist_documents(h.service, ctx, snapshot, [doc])
    assert repo.get("alice", "artifact", row["id"], include_deleted=True)["status"] == "deleted"
    h.finish()


@pytest.mark.parametrize("mode", ["cancelled", "profile", "source", "private", "crisis", "mutated"])
def test_changed_authority_or_content_never_stores_documents(repo: PostgresRepository, mode: str) -> None:
    h, ctx, snapshot, doc, facts = prepared(repo)
    if mode == "cancelled":
        h.finish()
    elif mode == "profile":
        repo.update("alice", "fact", facts[0]["id"], {"value": "女"}, expected_revision=facts[0]["revision"])
    elif mode == "source":
        row = repo.get("alice", "message", h.source["id"])
        repo.delete("alice", "message", row["id"], expected_revision=row["revision"])
    elif mode == "private":
        ctx = replace(ctx, incognito=True)
    elif mode == "crisis":
        ctx = replace(ctx, crisis=True)
    else:
        doc = deepcopy(doc)
        doc["references"] = [{"pointer": "/made-up"}]
    with pytest.raises((CoreError, ScopeError, EvidenceError)):
        persist_documents(h.service, ctx, snapshot, [doc])
    assert repo.list("alice", "artifact") == []
    if mode != "cancelled":
        h.finish()

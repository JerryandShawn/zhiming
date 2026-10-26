"""Native document/Pointer persistence, exact replay, closure and withdrawals."""

from copy import deepcopy

import pytest

from mingjing_core.adapters.charts.tool_evidence import evidence_result
from mingjing_core.application.charts_documents import verify_p8_document
from mingjing_core.application.p8_reference_records import (
    persist_reference_bundle,
    selected_references,
    verify_reference_bundle,
)
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.dependencies import entity_dependency

from .test_p8_documents_pg import prepared, repository  # noqa: F401


def with_rules(repo, count=1):
    h, ctx, snapshot, original, facts = prepared(repo)
    scope = original["scope"]
    data = {"value" + str(i): i for i in range(count)}
    rules = [
        {
            "met": True,
            "rule_id": "synthetic-" + str(i),
            "school": "synthetic",
            "source": "fixture",
            "evidence_paths": ["/data/value" + str(i)],
        }
        for i in range(count)
    ]
    payload = evidence_result("p8-daily-transit-v1", data, rules, [], scope)
    doc = verify_p8_document(
        payload,
        kind="daily_transit",
        owner=ctx.owner,
        subject=ctx.subject,
        revision=snapshot["revision"],
        operation_id=ctx.operation_id,
        source_sha256=original["source_sha256"],
    )
    return h, ctx, snapshot, doc, facts


def test_reference_replay_has_distinct_chart_rule_and_document_dependencies(repo) -> None:
    h, ctx, snapshot, doc, _ = with_rules(repo)
    bundle = persist_reference_bundle(h.service, ctx, snapshot, [doc])
    assert persist_reference_bundle(h.service, ctx, snapshot, [doc]) == bundle
    rows, versions = verify_reference_bundle(h.service, ctx, snapshot, [doc], bundle)
    assert len(rows) == 2 and len(repo.list("alice", "artifact")) == 2
    assert len(repo.list("alice", "interpretive_claim")) == 1
    assert {row["basis"] for row in rows} == {"p8_validated_chart", "p8_validated_rule"}
    assert len({row["id"] for row in rows}) == 2
    assert versions[entity_dependency("artifact", bundle["documents"][0]["id"])] == 1
    assert all(versions[entity_dependency(row["kind"], row["id"])] == row["revision"] for row in rows)
    assert all(key in versions for key in snapshot["versions"])
    assert repo.verify_versions("alice", versions)
    h.finish()


def test_ten_reference_limit_keeps_every_selected_rules_actual_chart_dependencies(repo) -> None:
    h, ctx, snapshot, doc, _ = with_rules(repo, count=18)
    refs = selected_references([doc])
    assert len(refs) == 10
    assert all(
        any(c["pointer"] == path and c["kind"] == "chart" for c in refs)
        for r in refs
        if r["kind"] == "rule"
        for path in r["evidence_pointers"]
    )
    bundle = persist_reference_bundle(h.service, ctx, snapshot, [doc])
    rows, _ = verify_reference_bundle(h.service, ctx, snapshot, [doc], bundle)
    assert len(rows) == 10
    h.finish()


@pytest.mark.parametrize(
    "mode",
    [
        "document_deleted",
        "reference_deleted",
        "reference_changed",
        "document_changed",
        "profile_changed",
        "duplicate_record",
        "missing_record",
        "wrong_revision",
        "cancelled",
    ],
)
def test_reference_attestation_refuses_changed_authority_or_forged_projection(repo, mode: str) -> None:
    h, ctx, snapshot, doc, facts = with_rules(repo)
    bundle = persist_reference_bundle(h.service, ctx, snapshot, [doc])
    if mode == "document_deleted":
        row = bundle["documents"][0]
        repo.delete("alice", "artifact", row["id"], expected_revision=row["revision"])
    elif mode == "reference_deleted":
        row = bundle["claims"][0]
        repo.delete("alice", "interpretive_claim", row["id"], expected_revision=row["revision"])
    elif mode in {"reference_changed", "document_changed"}:
        row = bundle["artifacts" if mode == "reference_changed" else "documents"][0]
        repo.update(
            "alice", "artifact", row["id"], {"p8_reference": {"pointer": "/fake"}}, expected_revision=row["revision"]
        )
    elif mode == "profile_changed":
        repo.update("alice", "fact", facts[0]["id"], {"value": "女"}, expected_revision=facts[0]["revision"])
    elif mode == "duplicate_record":
        bundle["claims"].append(deepcopy(bundle["claims"][0]))
    elif mode == "missing_record":
        bundle["artifacts"] = []
    elif mode == "wrong_revision":
        bundle["claims"][0]["revision"] = True
    else:
        h.finish()
    with pytest.raises(CoreError):
        verify_reference_bundle(h.service, ctx, snapshot, [doc], bundle)
    if mode != "cancelled":
        h.finish()


def test_withdrawn_reference_is_not_recreated_by_original_step(repo) -> None:
    h, ctx, snapshot, doc, _ = with_rules(repo)
    bundle = persist_reference_bundle(h.service, ctx, snapshot, [doc])
    row = bundle["claims"][0]
    repo.delete("alice", "interpretive_claim", row["id"], expected_revision=row["revision"])
    before = len(repo.list("alice", "artifact"))
    with pytest.raises(CoreError):
        persist_reference_bundle(h.service, ctx, snapshot, [doc])
    assert len(repo.list("alice", "artifact")) == before
    assert repo.get("alice", "interpretive_claim", row["id"], include_deleted=True)["status"] == "deleted"
    h.finish()

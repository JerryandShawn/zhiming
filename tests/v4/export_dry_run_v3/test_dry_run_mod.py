"""Synthetic dry-run/source/undo safety, without any database or effect adapter."""

import json
import random
from dataclasses import replace
from datetime import timedelta

import pytest

from mingjing_core.organize._change_values import LABEL_FIELDS, FieldValue
from mingjing_core.organize.export_dry_run_v3 import (
    DryRunError,
    DryRunLedger,
    ExportSnapshot,
    dry_run_export,
    plan_undo_dry_run,
    preview_dry_run,
)
from mingjing_core.organize.export_dry_run_v3.plan_values import plan_fingerprint
from mingjing_core.streaming.json_values import json_object

from .support_mod import FIXTURE, material, retext, synthetic_post_state


def test_synthetic_conversion_preserves_originals_and_both_roles() -> None:
    payload, snapshot, clock = material()
    before = json_object(snapshot.document)
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert plan.requires_user_review and plan.change_set.ops
    assert json_object(snapshot.document) == before and payload == FIXTURE["export"]
    assert all(op.collection == "topics" or op.field in LABEL_FIELDS for op in plan.change_set.ops)
    changed = {item.id for item in plan.preconditions}
    assert {"m002", "m003", "m004", "m005"} <= changed
    assert "m001" in plan.waiting_ids and {"m006", "m007", "m009"} <= set(plan.waiting_ids)
    assert any(
        item.entity_id == "m008" and item.reason_code == "sensitive_confirmation_required" for item in plan.conflicts
    )
    for anchor in plan.anchors:
        source = next(item for item in snapshot.sources if item.id == anchor.source_id)
        assert anchor.quote == source.text and anchor.revision == source.revision


def test_preview_has_only_bounded_user_samples_counts_and_conflicts() -> None:
    payload, snapshot, clock = material()
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    data = preview_dry_run(plan, snapshot=snapshot, scope=snapshot.scope, clock=clock)
    assert data["dry_run"] and data["requires_user_review"]
    assert data["counts"]["export_messages"] == 11
    assert all(len(item["sample"]) <= 80 and len(item["title"]) <= 80 for item in data["topics"])
    assert FIXTURE["texts"]["health"] not in json.dumps(data, ensure_ascii=False)
    assert FIXTURE["texts"]["assistant"] not in json.dumps(data, ensure_ascii=False)
    assert FIXTURE["texts"]["career"] not in repr(plan)


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_export_cannot_claim_a_different_scope(field: str) -> None:
    payload, snapshot, clock = material()
    payload[field] = "synthetic-other"
    with pytest.raises(DryRunError):
        dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_one_foreign_export_row_rejects_whole_batch(field: str) -> None:
    payload, snapshot, clock = material()
    payload["messages"][1][field] = "synthetic-other"
    with pytest.raises(DryRunError):
        dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")


@pytest.mark.parametrize("field", ["revision", "source_epoch"])
@pytest.mark.parametrize("value", [True, -1, 999])
def test_snapshot_preconditions_are_real_integers_and_exact(field: str, value: int) -> None:
    payload, snapshot, clock = material()
    payload[field] = value
    with pytest.raises(DryRunError):
        dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")


@pytest.mark.parametrize("field", ["content", "source_revision", "revision", "role", "at_ms", "thread_id"])
def test_exported_original_cannot_replace_current_host_row(field: str) -> None:
    payload, snapshot, clock = material()
    row = payload["messages"][1]
    row[field] = row[field] + 1 if type(row[field]) is int else FIXTURE["texts"]["alternate"]
    if field == "thread_id":
        row[field] = "synthetic-other-thread"
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert "m002" not in {item.id for item in plan.preconditions}
    assert any(item.entity_id == "m002" and item.reason_code == "row_changed" for item in plan.conflicts)


@pytest.mark.parametrize("field", ["active", "revoked", "incognito", "optout"])
def test_lifecycle_source_blocks_row_and_does_not_reassign_its_answer(field: str) -> None:
    payload, snapshot, clock = material()
    bad = replace(snapshot.sources[1], **{field: field != "active"})
    snapshot = replace(snapshot, sources=(snapshot.sources[0], bad, *snapshot.sources[2:]))
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert not {"m002", "m003"} & {item.id for item in plan.preconditions}
    assert "m003" in plan.waiting_ids


@pytest.mark.parametrize("key", ["secret", "profile", "optout", "health"])
def test_sensitive_or_secret_text_is_not_an_operation_or_sample(key: str) -> None:
    payload, snapshot, clock = material()
    snapshot = retext(payload, snapshot, "m002", key)
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert "m002" not in {item.id for item in plan.preconditions}
    assert FIXTURE["texts"][key] not in json.dumps(
        preview_dry_run(plan, snapshot=snapshot, scope=snapshot.scope, clock=clock), ensure_ascii=False
    )


def test_same_operation_replays_but_cannot_change_input_or_come_back_after_undo() -> None:
    payload, snapshot, clock = material()
    first = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    ledger = DryRunLedger("op-one", first.input_fingerprint, first.fingerprint)
    snapshot = replace(snapshot, operations=(ledger,))
    second = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert second.fingerprint == first.fingerprint and second.replayed
    payload["export_id"] = "synthetic-export-other"
    with pytest.raises(DryRunError):
        dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    snapshot = replace(snapshot, operations=(replace(ledger, state="undone"),))
    with pytest.raises(DryRunError):
        dry_run_export(FIXTURE["export"], snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")


def test_preview_rebuild_rejects_resealed_operation_tampering() -> None:
    payload, snapshot, clock = material()
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    op = next(item for item in plan.change_set.ops if item.collection == "messages")
    forged = replace(op, after=FieldValue(True, '"synthetic-foreign"'))
    changed = replace(
        plan,
        change_set=replace(plan.change_set, ops=tuple(forged if item is op else item for item in plan.change_set.ops)),
    )
    changed = replace(changed, fingerprint=plan_fingerprint(changed))
    with pytest.raises(DryRunError):
        preview_dry_run(changed, snapshot=snapshot, scope=snapshot.scope, clock=clock)


def test_undo_is_a_plan_only_and_restores_missing_vs_null_in_private_copy() -> None:
    payload, snapshot, clock = material()
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert not plan_undo_dry_run(plan, snapshot=snapshot, scope=snapshot.scope, clock=clock).allowed
    after = synthetic_post_state(plan, snapshot)
    inverse = plan_undo_dry_run(plan, snapshot=after, scope=after.scope, clock=clock)
    assert inverse.allowed and inverse.inverse_ops == plan.change_set.inverse_ops
    restored = json_object(after.document)
    for op in inverse.inverse_ops:
        target = restored[op.collection]
        key = op.entity_id
        if op.field is not None:
            target, key = target[key], op.field
        if op.after.present:
            target[key] = op.after.value
        else:
            target.pop(key, None)
    assert restored == json_object(snapshot.document)


@pytest.mark.parametrize("mutation", ["source", "epoch", "revision", "label", "row_revision"])
def test_undo_has_no_inverse_when_current_evidence_changed(mutation: str) -> None:
    payload, snapshot, clock = material()
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    after = synthetic_post_state(plan, snapshot)
    if mutation == "source":
        after = replace(after, sources=tuple(replace(item, revoked=True) for item in after.sources))
    elif mutation in {"epoch", "revision"}:
        field = "source_epoch" if mutation == "epoch" else "revision"
        after = replace(after, **{field: getattr(after, field) + 1})
    else:
        document = json_object(after.document)
        row = document["messages"][plan.preconditions[0].id]
        row["route_confidence" if mutation == "label" else "revision"] = 0.01 if mutation == "label" else 99
        after = replace(after, document=document)
    result = plan_undo_dry_run(plan, snapshot=after, scope=after.scope, clock=clock)
    assert not result.allowed and not result.inverse_ops and result.conflicts


def test_snapshot_defaults_to_not_authorized_for_synthetic_conversion() -> None:
    _, snapshot, _ = material()
    with pytest.raises(DryRunError):
        ExportSnapshot(snapshot.scope, snapshot.revision, snapshot.source_epoch, snapshot.document, snapshot.sources)


def test_100_random_source_clock_and_label_presence_round_trips() -> None:
    rng = random.Random(3306)
    for index in range(100):
        payload, snapshot, clock = material()
        clock.advance(timedelta(seconds=rng.randrange(0, 86400)))
        document = json_object(snapshot.document)
        if index % 2:
            document["messages"]["m002"]["space_secondary"] = None
        else:
            document["messages"]["m002"].pop("space_secondary", None)
        snapshot = replace(snapshot, document=document)
        plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id=f"op-{index}")
        after = synthetic_post_state(plan, snapshot)
        undo = plan_undo_dry_run(plan, snapshot=after, scope=after.scope, clock=clock)
        assert undo.allowed and undo.inverse_ops == plan.change_set.inverse_ops

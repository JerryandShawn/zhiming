"""Current snapshot, role association, lifecycle and undo-collision boundaries."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.organize.export_dry_run_v3 import DryRunError, dry_run_export, plan_undo_dry_run, preview_dry_run
from mingjing_core.streaming.json_values import json_object

from .support_mod import FIXTURE, material, synthetic_post_state


@pytest.mark.parametrize("field", ["status", "incognito", "retention_scope", "current", "deleted_at", "revoked_at"])
def test_current_row_not_export_claim_controls_lifecycle(field: str) -> None:
    payload, snapshot, clock = material()
    document = json_object(snapshot.document)
    values = {
        "status": "withdrawn",
        "incognito": True,
        "retention_scope": "temporary",
        "current": False,
        "deleted_at": "synthetic-mark",
        "revoked_at": "synthetic-mark",
    }
    document["messages"]["m002"][field] = values[field]
    snapshot = replace(snapshot, document=document)
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert not {"m002", "m003"} & {item.id for item in plan.preconditions}
    assert "m003" in plan.waiting_ids


@pytest.mark.parametrize("kind", ["row_owner", "source_owner", "requested_subject"])
def test_host_and_requested_scope_are_checked_before_any_preview(kind: str) -> None:
    payload, snapshot, clock = material()
    scope = snapshot.scope
    if kind == "row_owner":
        document = json_object(snapshot.document)
        document["messages"]["m002"]["owner_id"] = "synthetic-other"
        snapshot = replace(snapshot, document=document)
    elif kind == "source_owner":
        snapshot = replace(
            snapshot, sources=(replace(snapshot.sources[0], owner_id="synthetic-other"), *snapshot.sources[1:])
        )
    else:
        scope = replace(scope, subject_id="synthetic-other")
    with pytest.raises(DryRunError):
        dry_run_export(payload, snapshot=snapshot, scope=scope, clock=clock, operation_id="op-one")


@pytest.mark.parametrize(
    "field", ["schema", "synthetic", "extra_root", "extra_row", "duplicate_row", "duplicate_source"]
)
def test_explicit_synthetic_codec_does_not_accept_ambiguous_formats(field: str) -> None:
    payload, snapshot, clock = material()
    if field in {"schema", "synthetic"}:
        payload[field] = False
    elif field == "extra_root":
        payload["unexpected"] = True
    elif field == "extra_row":
        payload["messages"][0]["unexpected"] = True
    elif field == "duplicate_row":
        payload["messages"].append(dict(payload["messages"][0]))
    else:
        payload["messages"][1]["source_id"] = payload["messages"][0]["source_id"]
    with pytest.raises(DryRunError):
        dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")


@pytest.mark.parametrize(("gap_ms", "inherited"), [(0, False), (21600000, True), (21600001, False)])
def test_assistant_inheritance_uses_strict_prior_time_and_six_hour_limit(gap_ms: int, inherited: bool) -> None:
    payload, snapshot, clock = material()
    user, answer = (dict(payload["messages"][index]) for index in (1, 2))
    answer["at_ms"] = user["at_ms"] + gap_ms
    payload["messages"] = [user, answer]
    document = json_object(snapshot.document)
    document["messages"][answer["id"]]["at_ms"] = answer["at_ms"]
    sources = tuple(
        replace(item, at=datetime.fromtimestamp(answer["at_ms"] / 1000, UTC))
        if item.id == answer["source_id"]
        else item
        for item in snapshot.sources
    )
    snapshot = replace(snapshot, document=document, sources=sources)
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert (answer["id"] in {item.id for item in plan.preconditions}) is inherited
    assert (answer["id"] in plan.waiting_ids) is not inherited


def test_same_time_export_future_source_is_not_an_execution_now_fact() -> None:
    payload, snapshot, clock = material()
    row = payload["messages"][1]
    future = clock.now() + timedelta(seconds=1)
    row["at_ms"] = int(future.timestamp() * 1000)
    document = json_object(snapshot.document)
    document["messages"][row["id"]]["at_ms"] = row["at_ms"]
    sources = tuple(replace(item, at=future) if item.id == row["source_id"] else item for item in snapshot.sources)
    snapshot = replace(snapshot, document=document, sources=sources)
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert any(item.entity_id == row["id"] and item.reason_code == "source_future" for item in plan.conflicts)


def test_explicit_existing_user_route_is_not_overwritten_by_offline_classification() -> None:
    payload, snapshot, clock = material()
    document = json_object(snapshot.document)
    document["messages"]["m002"]["route_source"] = "user"
    snapshot = replace(snapshot, document=document)
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    assert "m002" not in {item.id for item in plan.preconditions}
    assert any(
        item.entity_id == "m002" and item.reason_code == "existing_route_requires_review" for item in plan.conflicts
    )
    assert json_object(snapshot.document) == document


def test_new_topic_identifier_collision_is_reported_instead_of_replacing_it() -> None:
    payload, snapshot, clock = material()
    first = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    created = next(op for op in first.change_set.ops if op.collection == "topics")
    document = json_object(snapshot.document)
    document["topics"][created.entity_id] = created.after.value
    snapshot = replace(snapshot, document=document)
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-two")
    assert any(item.reason_code == "topic_id_occupied" for item in plan.conflicts)
    assert all(item.entity_id != created.entity_id for item in plan.change_set.ops if item.collection == "topics")


@pytest.mark.parametrize("changed", ["source", "labels_without_revision"])
def test_preview_does_not_keep_stale_raw_samples(changed: str) -> None:
    payload, snapshot, clock = material()
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    if changed == "source":
        snapshot = replace(snapshot, sources=tuple(replace(item, revoked=True) for item in snapshot.sources))
    else:
        document = json_object(snapshot.document)
        document["messages"]["m002"]["space_secondary"] = "career"
        snapshot = replace(snapshot, document=document)
    with pytest.raises(DryRunError):
        preview_dry_run(plan, snapshot=snapshot, scope=snapshot.scope, clock=clock)


def test_later_message_reference_prevents_an_inverse_removing_the_new_topic() -> None:
    payload, snapshot, clock = material()
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    after = synthetic_post_state(plan, snapshot)
    document = json_object(after.document)
    new_topic = plan.topics[0]
    row = dict(document["messages"][new_topic.message_ids[0]], id="synthetic-later-message")
    document["messages"][row["id"]] = row
    after = replace(after, document=document)
    result = plan_undo_dry_run(plan, snapshot=after, scope=after.scope, clock=clock)
    assert not result.allowed and not result.inverse_ops
    assert any(item.reason_code == "later_topic_reference" for item in result.conflicts)


def test_fixed_exceptions_and_repr_do_not_expose_export_body() -> None:
    payload, snapshot, clock = material()
    payload["owner_id"] = "synthetic-other"
    with pytest.raises(DryRunError) as caught:
        dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    for text in FIXTURE["texts"].values():
        assert text not in str(caught.value) and text not in repr(snapshot)


@pytest.mark.parametrize("field", ["id", "source_id", "thread_id", "export_id", "operation_id"])
def test_opaque_metadata_cannot_be_used_to_echo_conversation_text(field: str) -> None:
    payload, snapshot, clock = material()
    operation_id = "op-one"
    if field == "operation_id":
        operation_id = FIXTURE["texts"]["career"]
    elif field == "export_id":
        payload[field] = FIXTURE["texts"]["career"]
    else:
        payload["messages"][0][field] = FIXTURE["texts"]["career"]
    with pytest.raises(DryRunError) as caught:
        dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id=operation_id)
    assert FIXTURE["texts"]["career"] not in str(caught.value)


def test_applied_global_revision_must_advance_past_the_reviewed_plan() -> None:
    payload, snapshot, clock = material()
    plan = dry_run_export(payload, snapshot=snapshot, scope=snapshot.scope, clock=clock, operation_id="op-one")
    after = synthetic_post_state(plan, snapshot)
    ledger = replace(after.operations[0], applied_revision=plan.expected_revision)
    after = replace(after, revision=plan.expected_revision, operations=(ledger,))
    inverse = plan_undo_dry_run(plan, snapshot=after, scope=after.scope, clock=clock)
    assert not inverse.allowed and not inverse.inverse_ops

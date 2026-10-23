"""Independent frozen protocol assertions. No real application, exporter, model or database is exercised."""

import json
import random
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import pytest

from mingjing_core.organize.export_dry_run_v3 import (
    DryRunLedger,
    dry_run_export,
    plan_undo_dry_run,
    preview_dry_run,
)
from mingjing_core.streaming.json_values import thaw_json

from .acceptance_core_support import (
    AT,
    CLOCK,
    INVALID_UNDO_STATES,
    SCOPE,
    TEXTS,
    applied,
    apply_fields,
    changed_document,
    fixture,
    message,
)


def plan(payload, snapshot, *, operation="synthetic-independent-op", scope=SCOPE):
    return dry_run_export(payload, snapshot=snapshot, scope=scope, clock=CLOCK, operation_id=operation)


def assert_blocked(payload, snapshot):
    try:
        candidate = plan(payload, snapshot)
    except ValueError as error:
        assert all(body not in str(error) for body in TEXTS.values())
        return
    assert not candidate.change_set.ops and not candidate.topics
    preview = preview_dry_run(candidate, snapshot=snapshot, scope=SCOPE, clock=CLOCK)
    assert all(body not in json.dumps(preview, ensure_ascii=False) for body in TEXTS.values())


@pytest.mark.parametrize("shape", ["actual", "unsupported", "nonsynthetic", "missing", "extra", "truthy"])
def test_unverified_actual_export_shapes_and_untrusted_schema_are_rejected(shape):
    payload, snapshot = fixture()
    if shape == "actual":
        payload = {"conversations": payload["messages"]}
    elif shape == "unsupported":
        payload["schema"] = "actual-v3-export-format-not-verified"
    elif shape == "nonsynthetic":
        payload["synthetic"] = False
    elif shape == "truthy":
        payload["synthetic"] = "true"
    elif shape == "missing":
        payload.pop("source_epoch")
    else:
        payload["database_url"] = "not-a-real-url"
    with pytest.raises(ValueError):
        plan(payload, snapshot)


@pytest.mark.parametrize(
    "key,value",
    [
        ("owner_id", "foreign-owner"),
        ("subject_id", "foreign-subject"),
        ("revision", 5),
        ("source_epoch", 7),
        ("revision", True),
    ],
)
def test_scope_revision_and_epoch_do_not_trust_export_claims(key, value):
    payload, snapshot = fixture()
    payload[key] = value
    with pytest.raises(ValueError) as error:
        plan(payload, snapshot)
    assert TEXTS["career"] not in str(error.value)


@pytest.mark.parametrize(
    "key,value",
    [
        ("revision", 2),
        ("source_revision", 2),
        ("source_id", "absent-source"),
        ("role", "assistant"),
        ("thread_id", "other-thread"),
        ("at_ms", 0),
        ("id", "absent-message"),
        ("content", ""),
    ],
)
def test_raw_immutable_row_drift_produces_no_operation(key, value):
    payload, snapshot = fixture()
    payload["messages"][0][key] = value
    assert_blocked(payload, snapshot)


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_foreign_current_row_is_controlled_without_original_body(field):
    payload, snapshot = fixture()
    snapshot = changed_document(
        snapshot, lambda document: document["messages"][message()["id"]].update({field: "foreign"})
    )
    with pytest.raises(ValueError) as error:
        plan(payload, snapshot)
    assert TEXTS["career"] not in str(error.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": 2},
        {"text": ""},
        {"role": "assistant"},
        {"origin": "other_user"},
        {"active": False},
        {"revoked": True},
        {"incognito": True},
        {"optout": True},
        {"at": AT + timedelta(seconds=1)},
    ],
)
def test_current_original_source_is_rechecked_even_without_epoch_advance(changes):
    payload, snapshot = fixture()
    snapshot = replace(snapshot, sources=(replace(snapshot.sources[0], **changes),))
    assert_blocked(payload, snapshot)


@pytest.mark.parametrize("text_key", ["health", "birth", "secret", "optout"])
def test_sensitive_or_forbidden_text_is_not_in_operations_or_preview(text_key):
    payload, snapshot = fixture(message(text_key=text_key))
    assert_blocked(payload, snapshot)


def test_clear_user_and_later_same_thread_answer_can_be_grouped_without_mutating_originals():
    payload, snapshot = fixture(message(), message(2, text_key="answer", role="assistant", seconds=1))
    original, host = deepcopy(payload), thaw_json(snapshot.document)
    candidate = plan(payload, snapshot)
    assert candidate.change_set.ops and candidate.topics and candidate.requires_user_review is True
    assert all(operation.collection in {"messages", "topics"} for operation in candidate.change_set.ops)
    assert all(
        operation.field in {None, "space_id", "topic_id", "space_secondary", "route_source", "route_confidence"}
        for operation in candidate.change_set.ops
    )
    assert set(candidate.topics[0].message_ids) == {row["id"] for row in payload["messages"]}
    assert payload == original and thaw_json(snapshot.document) == host
    assert all(body not in repr(candidate) for body in TEXTS.values())


@pytest.mark.parametrize("seconds,thread", [(0, "synthetic-thread"), (21601, "synthetic-thread"), (1, "other-thread")])
def test_assistant_cannot_inherit_equal_time_late_or_other_thread_user(seconds, thread):
    answer = message(2, text_key="answer", role="assistant", seconds=seconds, thread=thread)
    payload, snapshot = fixture(message(), answer)
    candidate = plan(payload, snapshot)
    assert answer["id"] in candidate.waiting_ids
    assert all(answer["id"] not in topic.message_ids for topic in candidate.topics)


def test_uncertainty_and_user_selected_labels_do_not_get_overwritten():
    payload, snapshot = fixture(message(text_key="uncertain"))
    candidate = plan(payload, snapshot)
    assert candidate.waiting_ids == (message()["id"],) and not candidate.change_set.ops
    payload, snapshot = fixture(labels={"space_id": "finance", "route_source": "user"})
    candidate = plan(payload, snapshot)
    assert not candidate.change_set.ops


@pytest.mark.parametrize("labels", [{}, {"space_id": None}, {"route_confidence": None}])
def test_apply_inverse_simulation_restores_absent_and_null_fields_exactly(labels):
    payload, snapshot = fixture(labels=labels)
    candidate = plan(payload, snapshot)
    assert candidate.change_set.ops
    current = applied(snapshot, candidate)
    undo = plan_undo_dry_run(candidate, snapshot=current, scope=SCOPE, clock=CLOCK)
    assert undo.allowed and undo.inverse_ops == candidate.change_set.inverse_ops
    restored = apply_fields(thaw_json(current.document), undo.inverse_ops)
    assert restored == thaw_json(snapshot.document)
    for key in labels:
        assert key in restored["messages"][message()["id"]] and restored["messages"][message()["id"]][key] is None


def test_preview_is_review_only_and_caps_samples_and_titles():
    payload, snapshot = fixture(message(text_key="career_long"))
    candidate = plan(payload, snapshot)
    preview = preview_dry_run(candidate, snapshot=snapshot, scope=SCOPE, clock=CLOCK)
    assert preview["dry_run"] is True and preview["requires_user_review"] is True
    assert preview["topics"] and all(len(row["title"]) <= 80 and len(row["sample"]) <= 80 for row in preview["topics"])
    assert not hasattr(candidate, "apply")


def test_replay_binds_both_raw_input_and_exact_plan_fingerprint():
    payload, snapshot = fixture()
    candidate = plan(payload, snapshot)
    assert plan(payload, snapshot) == candidate
    prior = DryRunLedger(candidate.operation_id, candidate.input_fingerprint, candidate.fingerprint)
    replay = plan(payload, replace(snapshot, operations=(prior,)))
    assert replay.replayed is True and replay.fingerprint == candidate.fingerprint
    for invalid in (
        replace(prior, input_fingerprint="0" * 64),
        replace(prior, plan_fingerprint="0" * 64),
        replace(prior, state="undone"),
    ):
        with pytest.raises(ValueError):
            plan(payload, replace(snapshot, operations=(invalid,)))


@pytest.mark.parametrize("state", INVALID_UNDO_STATES)
def test_undo_requires_host_applied_ledger_and_all_current_revisions(state):
    payload, snapshot = fixture()
    candidate = plan(payload, snapshot)
    current = applied(snapshot, candidate)
    ledger = current.operations[0]
    if state == "missing":
        current = replace(current, operations=())
    elif state == "planned":
        current = replace(
            current, operations=(replace(ledger, state="planned", applied_revision=None, target_revisions=()),)
        )
    elif state == "wrong_plan":
        current = replace(current, operations=(replace(ledger, plan_fingerprint="0" * 64),))
    elif state == "wrong_input":
        current = replace(current, operations=(replace(ledger, input_fingerprint="0" * 64),))
    elif state == "wrong_global":
        current = replace(current, revision=current.revision + 1)
    elif state == "missing_target":
        current = replace(current, operations=(replace(ledger, target_revisions=()),))
    elif state == "extra_target":
        current = replace(
            current, operations=(replace(ledger, target_revisions=(*ledger.target_revisions, ("extra", 1))),)
        )
    elif state in {"same_global", "older_global"}:
        revision = candidate.expected_revision - int(state == "older_global")
        current = replace(current, revision=revision, operations=(replace(ledger, applied_revision=revision),))
    else:
        current = replace(current, operations=(replace(ledger, target_revisions=((message()["id"], 2),)),))
    undo = plan_undo_dry_run(candidate, snapshot=current, scope=SCOPE, clock=CLOCK)
    assert not undo.allowed and undo.conflicts and not undo.inverse_ops


@pytest.mark.parametrize(
    "changes",
    [{"active": False}, {"revoked": True}, {"incognito": True}, {"optout": True}, {"revision": 2}, {"text": ""}],
)
def test_undo_cannot_restore_labels_after_source_withdrawal_without_epoch_change(changes):
    payload, snapshot = fixture()
    candidate = plan(payload, snapshot)
    current = applied(snapshot, candidate)
    current = replace(current, sources=(replace(current.sources[0], **changes),))
    undo = plan_undo_dry_run(candidate, snapshot=current, scope=SCOPE, clock=CLOCK)
    assert not undo.allowed and undo.conflicts and not undo.inverse_ops


@pytest.mark.parametrize("field,value", [("space_id", "wellbeing"), ("content", ""), ("revision", 3)])
def test_undo_does_not_overwrite_concurrent_labels_or_original_row_edit(field, value):
    payload, snapshot = fixture()
    candidate = plan(payload, snapshot)
    current = applied(snapshot, candidate)

    def mutate(document):
        row = document["messages"][message()["id"]]
        row[field] = value
        # Keep the concurrent graph valid: a topic's message and owning area move together.
        if field == "space_id":
            document["topics"][row["topic_id"]]["space_id"] = value

    current = changed_document(current, mutate)
    undo = plan_undo_dry_run(candidate, snapshot=current, scope=SCOPE, clock=CLOCK)
    assert not undo.allowed and not undo.inverse_ops


def test_undone_ledger_replay_is_an_explicit_noop():
    payload, snapshot = fixture()
    candidate = plan(payload, snapshot)
    ledger = DryRunLedger(candidate.operation_id, candidate.input_fingerprint, candidate.fingerprint, "undone")
    undo = plan_undo_dry_run(candidate, snapshot=replace(snapshot, operations=(ledger,)), scope=SCOPE, clock=CLOCK)
    assert undo.already_undone and not undo.allowed and not undo.inverse_ops


@pytest.mark.parametrize("field", ["fingerprint", "original_payload", "operation_id"])
def test_tampering_is_rejected_by_both_preview_and_undo(field):
    payload, snapshot = fixture()
    candidate = plan(payload, snapshot)
    value = "0" * 64 if field == "fingerprint" else {} if field == "original_payload" else "forged-operation"
    candidate = replace(candidate, **{field: value})
    for function in (preview_dry_run, plan_undo_dry_run):
        with pytest.raises(ValueError):
            function(candidate, snapshot=snapshot, scope=SCOPE, clock=CLOCK)


def test_hundred_pure_plan_replays_preserve_missing_null_and_original_sources():
    rng = random.Random(336)
    for _ in range(100):
        labels = rng.choice(({}, {"space_id": None}, {"route_confidence": None}))
        payload, snapshot = fixture(labels=labels)
        before = deepcopy(payload)
        candidate = plan(payload, snapshot)
        current = applied(snapshot, candidate)
        undo = plan_undo_dry_run(candidate, snapshot=current, scope=SCOPE, clock=CLOCK)
        assert undo.allowed
        assert apply_fields(thaw_json(current.document), undo.inverse_ops) == thaw_json(snapshot.document)
        assert payload == before and snapshot.sources[0].text == TEXTS["career"]


@pytest.mark.parametrize(
    "key,value", [("at_ms", True), ("revision", True), ("source_revision", True), ("at_ms", -1), ("role", "system")]
)
def test_row_numeric_boundaries_are_strict_and_system_cannot_be_imported(key, value):
    payload, snapshot = fixture()
    payload["messages"][0][key] = value
    assert_blocked(payload, snapshot)


@pytest.mark.parametrize("key", ["content", "source_revision", "thread_id"])
def test_missing_or_extra_row_fields_do_not_get_inferred(key):
    payload, snapshot = fixture()
    payload["messages"][0].pop(key)
    with pytest.raises(ValueError):
        plan(payload, snapshot)
    payload, snapshot = fixture()
    payload["messages"][0]["unverified_extra"] = None
    with pytest.raises(ValueError):
        plan(payload, snapshot)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "deleted"),
        ("incognito", True),
        ("current", False),
        ("retention_scope", "temporary"),
        ("content", ""),
        ("revision", 2),
    ],
)
def test_current_host_row_cannot_reactivate_stale_or_private_originals(field, value):
    payload, snapshot = fixture()
    snapshot = changed_document(snapshot, lambda document: document["messages"][message()["id"]].update({field: value}))
    assert_blocked(payload, snapshot)


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_foreign_raw_row_and_foreign_source_never_create_labels(field):
    payload, snapshot = fixture()
    payload["messages"][0][field] = "foreign"
    assert_blocked(payload, snapshot)
    payload, snapshot = fixture()
    snapshot = replace(snapshot, sources=(replace(snapshot.sources[0], **{field: "foreign"}),))
    assert_blocked(payload, snapshot)


def test_duplicate_export_message_and_current_source_are_rejected():
    payload, snapshot = fixture()
    payload["messages"].append(deepcopy(payload["messages"][0]))
    with pytest.raises(ValueError):
        plan(payload, snapshot)
    with pytest.raises(ValueError):
        replace(snapshot, sources=(snapshot.sources[0], snapshot.sources[0]))


def test_later_message_reference_prevents_deleting_a_created_topic_on_undo():
    payload, snapshot = fixture()
    candidate = plan(payload, snapshot)
    current = applied(snapshot, candidate)
    extra_payload, extra_host = fixture(message(2, seconds=60))
    row = thaw_json(extra_host.document)["messages"][extra_payload["messages"][0]["id"]]
    topic_id = candidate.topics[0].id
    row.update(space_id=candidate.topics[0].space_id, topic_id=topic_id)

    def mutate(document):
        document["messages"][row["id"]] = row
        document["topics"][topic_id]["message_ids"].append(row["id"])

    current = changed_document(current, mutate)
    current = replace(current, sources=(*current.sources, *extra_host.sources))
    undo = plan_undo_dry_run(candidate, snapshot=current, scope=SCOPE, clock=CLOCK)
    assert not undo.allowed and not undo.inverse_ops


@pytest.mark.parametrize("value", ["not opaque", "x\ny", "x" * 201])
def test_opaque_business_identifiers_cannot_smuggle_readable_text_into_conflicts(value):
    payload, snapshot = fixture()
    payload["messages"][0]["id"] = value
    with pytest.raises(ValueError):
        plan(payload, snapshot)

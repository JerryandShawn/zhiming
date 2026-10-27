"""An implicit old or new topic reference is a guarded source, even without a topic edit."""

from copy import deepcopy
from typing import Any

import pytest

from mingjing_core.organize._change_values import ChangeConflict
from mingjing_core.organize.changes import ChangeSet, MemoryChangeStore


def _documents(*, created: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    before = {
        "owner_id": "synthetic-owner",
        "subject_id": "synthetic-subject",
        "messages": {
            "m1": {
                "id": "m1",
                "owner_id": "synthetic-owner",
                "subject_id": "synthetic-subject",
                "content": "合成的原始正文",
                "at_ms": 1,
                "revision": 1,
                "status": "active",
                "topic_id": "t1",
                "space_id": "career",
            }
        },
        "topics": {
            identity: {
                "id": identity,
                "owner_id": "synthetic-owner",
                "subject_id": "synthetic-subject",
                "title": "合成话题",
                "space_id": "career",
                "status": "archived" if identity == "t1" else "open",
                "revision": 1,
            }
            for identity in (("t1", "t3") if created else ("t1", "t2", "t3"))
        },
        "untouched": {"nullable": None, "items": [1, 2]},
    }
    after = deepcopy(before)
    if created:
        after["topics"]["t2"] = dict(after["topics"]["t3"], id="t2", message_ids=["m1"])
    after["messages"]["m1"]["topic_id"] = "t2"
    return before, after


def _batch(before: dict[str, Any], after: dict[str, Any]) -> ChangeSet:
    return ChangeSet.from_documents(
        before,
        after,
        batch_id="topic-guard",
        owner_id="synthetic-owner",
        subject_id="synthetic-subject",
    )


@pytest.mark.parametrize("identity", ["t1", "t2"])
@pytest.mark.parametrize("status", ["revoked", "withdrawn", "deleted"])
@pytest.mark.parametrize("when", ["apply", "revert"])
def test_implicit_before_after_topic_cannot_be_revived(
    identity: str, status: str, when: str
) -> None:
    before, after = _documents()
    changes = _batch(before, after)
    assert all(op.collection == "messages" for op in changes.ops)
    store = MemoryChangeStore(before)
    if when == "revert":
        store.apply(changes)
    concurrent = store.document
    concurrent["topics"][identity]["status"] = status
    store.refresh(concurrent)
    with pytest.raises(ChangeConflict, match="停止使用"):
        store.revert(changes.batch_id) if when == "revert" else store.apply(changes)
    assert store.document == concurrent


@pytest.mark.parametrize("identity", ["t1", "t2"])
@pytest.mark.parametrize("when", ["apply", "revert"])
def test_implicit_topic_revision_is_part_of_atomic_preflight(
    identity: str, when: str
) -> None:
    before, after = _documents()
    changes = _batch(before, after)
    store = MemoryChangeStore(before)
    if when == "revert":
        store.apply(changes)
    concurrent = store.document
    concurrent["topics"][identity]["revision"] = 2
    store.refresh(concurrent)
    with pytest.raises(ChangeConflict, match="原文或修订"):
        store.revert(changes.batch_id) if when == "revert" else store.apply(changes)
    assert store.document == concurrent


@pytest.mark.parametrize("when", ["apply", "revert"])
def test_label_only_edit_guards_unchanged_topic_reference(when: str) -> None:
    before, _ = _documents()
    after = deepcopy(before)
    after["messages"]["m1"]["route_confidence"] = 0.8
    changes = _batch(before, after)
    assert all(op.field != "topic_id" for op in changes.ops)
    store = MemoryChangeStore(before)
    if when == "revert":
        store.apply(changes)
    concurrent = store.document
    concurrent["topics"]["t1"]["status"] = "withdrawn"
    store.refresh(concurrent)
    with pytest.raises(ChangeConflict, match="停止使用"):
        store.revert(changes.batch_id) if when == "revert" else store.apply(changes)
    assert store.document == concurrent


def test_created_topic_is_batch_owned_but_old_topic_is_guarded() -> None:
    before, after = _documents(created=True)
    changes = _batch(before, after)
    topic_guards = {
        guard.entity_id
        for guard in changes.source_guards
        if guard.collection == "topics"
    }
    assert topic_guards == {"t1"}
    store = MemoryChangeStore(before)
    assert store.apply(changes) == after
    assert store.revert(changes.batch_id) == before


@pytest.mark.parametrize("initial", ["missing", None, ""])
def test_missing_and_null_old_references_keep_distinct_undo(
    initial: str | None,
) -> None:
    before, _ = _documents()
    if initial == "missing":
        before["messages"]["m1"].pop("topic_id")
    else:
        before["messages"]["m1"]["topic_id"] = initial
    after = deepcopy(before)
    after["messages"]["m1"]["topic_id"] = "t2"
    changes = _batch(before, after)
    assert {
        guard.entity_id
        for guard in changes.source_guards
        if guard.collection == "topics"
    } == {"t2"}
    store = MemoryChangeStore(before)
    assert store.apply(changes) == after
    assert store.revert(changes.batch_id) == before


def test_partial_revert_preserves_later_topic_assignment_and_other_labels() -> None:
    before, after = _documents()
    after["messages"]["m1"].update(route_confidence=0.8, space_secondary="finance")
    changes = _batch(before, after)
    store = MemoryChangeStore(before)
    store.apply(changes)
    concurrent = store.document
    concurrent["messages"]["m1"].update(topic_id="t3", route_confidence=0.2)
    store.refresh(concurrent)
    reverted = store.revert(changes.batch_id)
    assert reverted["messages"]["m1"]["topic_id"] == "t3"
    assert reverted["messages"]["m1"]["route_confidence"] == 0.2
    assert "space_secondary" not in reverted["messages"]["m1"]
    assert {row["field"] for row in store.last_revert_conflicts} == {
        "topic_id",
        "route_confidence",
    }
    assert reverted["topics"]["t1"]["status"] == "archived"


@pytest.mark.parametrize("status", ["open", "closed", "archived"])
def test_valid_old_topic_lifecycle_is_preserved_without_active_coercion(
    status: str,
) -> None:
    before, _ = _documents()
    before["topics"]["t1"]["status"] = status
    after = deepcopy(before)
    after["messages"]["m1"]["topic_id"] = "t2"
    changes = _batch(before, after)
    store = MemoryChangeStore(before)
    assert store.apply(changes) == after
    assert store.revert(changes.batch_id) == before
    assert store.document["topics"]["t1"]["status"] == status

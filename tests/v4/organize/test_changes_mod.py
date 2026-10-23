"""Pure storage snapshots prove label-only atomicity and conservative undo semantics."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from mingjing_core.organize._change_values import (
    ChangeConflict,
    FieldChange,
    FieldValue,
)
from mingjing_core.organize.changes import ChangeSet, MemoryChangeStore


def document() -> dict[str, Any]:
    return {
        "owner_id": "synthetic-owner",
        "subject_id": "synthetic-subject",
        "untouched": {"items": [1, None, {"kind": "synthetic"}]},
        "messages": {
            "m1": {
                "id": "m1",
                "owner_id": "synthetic-owner",
                "subject_id": "synthetic-subject",
                "content": "合成的面试讨论",
                "at_ms": 1000,
                "revision": 1,
                "status": "active",
                "space_secondary": None,
            },
            "m2": {
                "id": "m2",
                "owner_id": "synthetic-owner",
                "subject_id": "synthetic-subject",
                "content": "合成的面试进展",
                "at_ms": 2000,
                "revision": 1,
                "status": "active",
            },
        },
        "topics": {
            "t1": {
                "id": "t1",
                "owner_id": "synthetic-owner",
                "subject_id": "synthetic-subject",
                "title": "面试",
                "space_id": "career",
                "status": "active",
                "message_ids": ["m1", "m2"],
                "untouched": {"nested": ["value"]},
            }
        },
    }


def changed(before: dict[str, Any]) -> dict[str, Any]:
    after = deepcopy(before)
    after["messages"]["m1"].update(
        space_id="career", topic_id="t1", space_secondary="finance", route_source="rule", route_confidence=0.9
    )
    after["messages"]["m2"].update(space_id="career", topic_id="t2", space_secondary=None)
    after["topics"]["t1"].update(title="跳槽面试", message_ids=["m1"])
    after["topics"]["t2"] = {
        "id": "t2",
        "owner_id": "synthetic-owner",
        "subject_id": "synthetic-subject",
        "title": "面试进展",
        "space_id": "career",
        "status": "active",
        "message_ids": ["m2"],
        "summary": "纯合成摘要",
    }
    return after


def batch(before: dict[str, Any], after: dict[str, Any], identity: str = "batch-1") -> ChangeSet:
    return ChangeSet.from_documents(
        before, after, batch_id=identity, owner_id="synthetic-owner", subject_id="synthetic-subject"
    )


def test_apply_revert_matches_every_field_and_serializes_inverse() -> None:
    before = document()
    after = changed(before)
    change_set = batch(before, after)
    serialized = change_set.as_dict()
    assert json.loads(json.dumps(serialized, ensure_ascii=False)) == serialized
    assert serialized["inverse_ops"] == [op.inverse().as_dict() for op in reversed(change_set.ops)]
    store = MemoryChangeStore(before)
    assert store.apply(change_set) == after
    assert store.revert(change_set.batch_id) == before
    assert store.revert(change_set.batch_id) == before
    assert "space_id" not in store.document["messages"]["m1"]
    assert store.document["messages"]["m1"]["space_secondary"] is None
    assert "space_secondary" not in store.document["messages"]["m2"]


def test_snapshots_and_return_values_are_defensive_copies() -> None:
    before = document()
    after = changed(before)
    change_set = batch(before, after)
    store = MemoryChangeStore(before)
    before["untouched"]["items"].clear()
    after["messages"]["m1"]["content"] = "外部更改"
    first = store.apply(change_set)
    first["untouched"]["items"].clear()
    projected = change_set.as_dict()
    projected["ops"][0]["after"]["value"] = "篡改序列化副本"
    assert store.document["untouched"]["items"] == [1, None, {"kind": "synthetic"}]
    assert store.document["messages"]["m1"]["content"] == "合成的面试讨论"
    assert store.revert("batch-1") == document()


def test_stable_batch_replay_is_idempotent_and_revert_tombstone_is_final() -> None:
    before = document()
    after = changed(before)
    store = MemoryChangeStore(before)
    change_set = batch(before, after)
    assert store.apply(change_set) == store.apply(change_set) == after
    store.revert("batch-1")
    with pytest.raises(ChangeConflict, match="已撤销"):
        store.apply(change_set)
    alternative = deepcopy(after)
    alternative["messages"]["m1"]["route_confidence"] = 0.7
    with pytest.raises(ChangeConflict, match="更换内容"):
        store.apply(batch(before, alternative))
    assert store.document == before


def test_conflict_preflight_leaves_entire_batch_untouched() -> None:
    before = document()
    change_set = batch(before, changed(before))
    concurrent = deepcopy(before)
    concurrent["messages"]["m2"]["space_id"] = "manual"
    store = MemoryChangeStore(concurrent)
    with pytest.raises(ChangeConflict, match="前置字段"):
        store.apply(change_set)
    assert store.document == concurrent
    assert "space_id" not in store.document["messages"]["m1"]


@pytest.mark.parametrize("field,value", [("content", "新正文"), ("at_ms", 3000), ("revision", 2)])
@pytest.mark.parametrize("when", ["apply", "revert"])
def test_original_or_revision_change_refuses_without_overwriting(field: str, value: Any, when: str) -> None:
    before = document()
    change_set = batch(before, changed(before))
    store = MemoryChangeStore(before)
    if when == "revert":
        store.apply(change_set)
    concurrent = store.document
    concurrent["messages"]["m1"][field] = value
    store.refresh(concurrent)
    with pytest.raises(ChangeConflict, match="原文或修订"):
        store.revert("batch-1") if when == "revert" else store.apply(change_set)
    assert store.document == concurrent


@pytest.mark.parametrize("status", ["revoked", "withdrawn", "deleted"])
@pytest.mark.parametrize("key", ["status", "source_status"])
@pytest.mark.parametrize("when", ["apply", "revert"])
def test_stopped_source_never_revives(status: str, key: str, when: str) -> None:
    before = document()
    change_set = batch(before, changed(before))
    store = MemoryChangeStore(before)
    if when == "revert":
        store.apply(change_set)
    concurrent = store.document
    concurrent["messages"]["m1"][key] = status
    store.refresh(concurrent)
    with pytest.raises(ChangeConflict, match="停止使用"):
        store.revert("batch-1") if when == "revert" else store.apply(change_set)
    assert store.document == concurrent


@pytest.mark.parametrize("when", ["apply", "revert"])
def test_missing_source_is_not_recreated(when: str) -> None:
    before = document()
    change_set = batch(before, changed(before))
    store = MemoryChangeStore(before)
    if when == "revert":
        store.apply(change_set)
    concurrent = store.document
    concurrent["messages"].pop("m1")
    for topic in concurrent["topics"].values():
        topic["message_ids"] = [identity for identity in topic["message_ids"] if identity != "m1"]
    store.refresh(concurrent)
    with pytest.raises(ChangeConflict, match="不存在"):
        store.revert("batch-1") if when == "revert" else store.apply(change_set)
    assert store.document == concurrent


def test_undo_preserves_later_label_and_topic_edits() -> None:
    before = document()
    change_set = batch(before, changed(before))
    store = MemoryChangeStore(before)
    store.apply(change_set)
    concurrent = store.document
    concurrent["messages"]["m1"]["space_id"] = "manual-space"
    concurrent["topics"]["t1"]["space_id"] = "manual-space"
    concurrent["topics"]["t1"]["title"] = "人工改名"
    concurrent["topics"]["t2"]["title"] = "后续保留新话题"
    store.refresh(concurrent)
    result = store.revert("batch-1")
    assert result["messages"]["m1"]["space_id"] == "manual-space"
    assert "topic_id" not in result["messages"]["m1"]
    assert result["topics"]["t1"]["title"] == "人工改名"
    assert result["topics"]["t1"]["message_ids"] == ["m1", "m2"]
    assert result["topics"]["t2"]["title"] == "后续保留新话题"
    conflicts = store.last_revert_conflicts
    assert {(row["collection"], row["entity_id"], row["field"]) for row in conflicts} == {
        ("messages", "m1", "space_id"),
        ("topics", "t1", "title"),
        ("topics", "t2", None),
    }
    assert "人工改名" not in json.dumps(conflicts, ensure_ascii=False)
    conflicts.clear()
    assert len(store.last_revert_conflicts) == 3


def test_undo_keeps_created_topic_referenced_by_a_later_message() -> None:
    before = document()
    store = MemoryChangeStore(before)
    store.apply(batch(before, changed(before)))
    concurrent = store.document
    concurrent["messages"]["m3"] = dict(concurrent["messages"]["m2"], id="m3", content="后续合成消息")
    store.refresh(concurrent)
    result = store.revert("batch-1")
    assert result["messages"]["m3"]["topic_id"] == "t2"
    assert "t2" in result["topics"]
    assert store.last_revert_conflicts[0]["reason"] == "later_references"


@pytest.mark.parametrize("target", ["global", "message", "topic"])
@pytest.mark.parametrize("key", ["owner_id", "subject_id"])
def test_cross_scope_documents_and_refresh_are_rejected(target: str, key: str) -> None:
    before = document()
    after = changed(before)
    record = (
        after
        if target == "global"
        else after["messages" if target == "message" else "topics"]["m1" if target == "message" else "t1"]
    )
    record[key] = "other"
    with pytest.raises(ChangeConflict, match="归属"):
        batch(before, after)
    store = MemoryChangeStore(before)
    with pytest.raises(ChangeConflict, match="归属"):
        store.refresh(after)
    assert store.document == before


@pytest.mark.parametrize("field,value", [("content", "篡改"), ("revision", 2), ("new_unknown", "value")])
def test_message_source_fields_are_not_editable(field: str, value: Any) -> None:
    before = document()
    after = changed(before)
    after["messages"]["m1"][field] = value
    with pytest.raises(ChangeConflict, match="只能修改"):
        batch(before, after)


@pytest.mark.parametrize("operation", ["add_message", "remove_message", "remove_topic", "global"])
def test_forbidden_document_operations(operation: str) -> None:
    before = document()
    after = deepcopy(before)
    if operation == "add_message":
        after["messages"]["m3"] = dict(after["messages"]["m1"], id="m3")
    elif operation == "remove_message":
        after["messages"].pop("m1")
        after["topics"]["t1"]["message_ids"] = ["m2"]
    elif operation == "remove_topic":
        after["topics"].pop("t1")
    else:
        after["untouched"]["items"] = [False]
    with pytest.raises(ChangeConflict):
        batch(before, after)


def test_forged_changes_cannot_bypass_label_only_or_missing_source_guards() -> None:
    before = document()
    valid = batch(before, changed(before))
    malicious = FieldChange(
        "messages", "m1", "content", FieldValue(True, '"合成的面试讨论"'), FieldValue(True, '"篡改"')
    )
    store = MemoryChangeStore(before)
    with pytest.raises(ChangeConflict):
        store.apply(replace(valid, ops=(malicious,)))
    with pytest.raises(ChangeConflict, match="来源防护"):
        store.apply(replace(valid, source_guards=()))
    assert store.document == before


def test_existing_topic_immutable_metadata_is_preserved() -> None:
    before = document()
    after = changed(before)
    after["topics"]["t1"]["untouched"]["nested"].append("not allowed")
    with pytest.raises(ChangeConflict, match="只能修改"):
        batch(before, after)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "key"}, (1, 2), object()])
def test_non_json_safe_snapshot_rejected(value: Any) -> None:
    before = document()
    before["untouched"] = value
    with pytest.raises(ChangeConflict):
        MemoryChangeStore(before)


def test_unknown_batch_cannot_be_undone() -> None:
    store = MemoryChangeStore(document())
    with pytest.raises(ChangeConflict, match="批次不存在"):
        store.revert("missing")


def test_topic_rename_also_guards_its_sources() -> None:
    before = document()
    after = deepcopy(before)
    after["topics"]["t1"]["title"] = "改名"
    change_set = batch(before, after)
    concurrent = deepcopy(before)
    concurrent["messages"]["m1"]["status"] = "withdrawn"
    store = MemoryChangeStore(concurrent)
    with pytest.raises(ChangeConflict, match="停止使用"):
        store.apply(change_set)
    assert store.document == concurrent


def test_same_batch_is_atomic_under_in_process_concurrent_replay() -> None:
    before = document()
    after = changed(before)
    change_set = batch(before, after)
    store = MemoryChangeStore(before)
    with ThreadPoolExecutor(max_workers=8) as executor:
        applied = list(executor.map(lambda _: store.apply(change_set), range(50)))
    assert all(value == after for value in applied)
    with ThreadPoolExecutor(max_workers=8) as executor:
        reverted = list(executor.map(lambda _: store.revert("batch-1"), range(50)))
    assert all(value == before for value in reverted)
    assert store.last_revert_conflicts == []


@pytest.mark.parametrize("when", ["apply", "revert"])
def test_topic_revision_guard_refuses_stale_batch_without_touching_labels(when: str) -> None:
    before = document()
    before["topics"]["t1"]["revision"] = 1
    change_set = batch(before, changed(before))
    assert any(guard.collection == "topics" and guard.entity_id == "t1" for guard in change_set.source_guards)
    store = MemoryChangeStore(before)
    if when == "revert":
        store.apply(change_set)
    concurrent = store.document
    concurrent["topics"]["t1"]["revision"] = 2
    store.refresh(concurrent)
    with pytest.raises(ChangeConflict, match="原文或修订"):
        store.revert("batch-1") if when == "revert" else store.apply(change_set)
    assert store.document == concurrent


def test_full_directory_refuses_dangling_message_topic_before_any_write() -> None:
    before = document()
    after = changed(before)
    after["messages"]["m1"]["topic_id"] = "missing-topic"
    with pytest.raises(ChangeConflict, match="完整目录"):
        batch(before, after)
    store = MemoryChangeStore(before)
    with pytest.raises(ChangeConflict, match="完整目录"):
        store.refresh(after)
    assert store.document == before


def test_message_and_referenced_topic_cannot_have_different_spaces() -> None:
    before = document()
    after = changed(before)
    after["messages"]["m1"]["space_id"] = "family"
    with pytest.raises(ChangeConflict, match="空间不一致"):
        batch(before, after)
    store = MemoryChangeStore(before)
    with pytest.raises(ChangeConflict, match="空间不一致"):
        store.refresh(after)
    assert store.document == before


@pytest.mark.parametrize(
    "metadata", [{"incognito": True}, {"thread_id": "incognito:synthetic"}, {"retention_scope": "temporary"}]
)
def test_persistent_store_refuses_temporary_or_incognito_sources(metadata: dict[str, Any]) -> None:
    before = document()
    change_set = batch(before, changed(before))
    store = MemoryChangeStore(before)
    temporary = store.document
    temporary["messages"]["m1"].update(metadata)
    store.refresh(temporary)
    with pytest.raises(ChangeConflict, match="无痕或临时"):
        store.apply(change_set)
    assert store.document == temporary
    with pytest.raises(ChangeConflict, match="无痕或临时"):
        batch(temporary, changed(temporary))

"""Label-only reversible batches; storage adapters must reload their snapshot before writes."""

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any

from ._change_values import (
    LABEL_FIELDS,
    TOPIC_FIELDS,
    ChangeConflict,
    FieldChange,
    FieldValue,
    SourceGuard,
    canonical,
    digest,
    immutable_message,
    immutable_topic,
    records,
    require_active,
    scope,
    validate_document,
)


def _field_changes(
    collection: str, identity: str, before: dict[str, Any], after: dict[str, Any], allowed: frozenset[str]
) -> list[FieldChange]:
    changes = []
    for key in sorted(set(before) | set(after)):
        old, new = FieldValue.read(before, key), FieldValue.read(after, key)
        if old != new:
            if key not in allowed:
                raise ChangeConflict("整理只能修改归区标签和话题元数据")
            changes.append(FieldChange(collection, identity, key, old, new))
    return changes


def _operations(before: dict[str, Any], after: dict[str, Any]) -> tuple[FieldChange, ...]:
    if canonical({key: value for key, value in before.items() if key not in {"messages", "topics"}}) != canonical(
        {key: value for key, value in after.items() if key not in {"messages", "topics"}}
    ):
        raise ChangeConflict("整理不能修改全局字段")
    old_messages, new_messages = records(before, "messages"), records(after, "messages")
    if set(old_messages) != set(new_messages):
        raise ChangeConflict("整理不能新增或删除原始消息")
    changes = []
    for identity, message in sorted(old_messages.items()):
        changes.extend(_field_changes("messages", identity, message, new_messages[identity], LABEL_FIELDS))
    old_topics, new_topics = records(before, "topics"), records(after, "topics")
    if set(old_topics) - set(new_topics):
        raise ChangeConflict("整理不能删除已有话题")
    for identity, topic in sorted(new_topics.items()):
        if identity not in old_topics:
            require_active(topic)
            changes.append(FieldChange("topics", identity, None, FieldValue(False), FieldValue(True, canonical(topic))))
        else:
            changes.extend(_field_changes("topics", identity, old_topics[identity], topic, TOPIC_FIELDS))
    return tuple(changes)


def _guards(before: dict[str, Any], ops: tuple[FieldChange, ...]) -> tuple[SourceGuard, ...]:
    message_ids: set[str] = set()
    for op in ops:
        if op.collection == "messages":
            message_ids.add(op.entity_id)
        else:
            message_ids.update(records(before, "topics").get(op.entity_id, {}).get("message_ids", []))
            if op.field == "message_ids" or op.field is None:
                for value in (op.before, op.after):
                    if value.present:
                        item = value.value
                        message_ids.update(item.get("message_ids", []) if op.field is None else item)
    guards = []
    for identity in sorted(message_ids):
        record = records(before, "messages")[identity]
        require_active(record)
        guards.append(SourceGuard("messages", identity, digest(immutable_message(record))))
    topic_ids = {op.entity_id for op in ops if op.collection == "topics"}
    for identity in sorted(topic_ids & set(records(before, "topics"))):
        record = records(before, "topics")[identity]
        require_active(record)
        guards.append(SourceGuard("topics", identity, digest(immutable_topic(record))))
    return tuple(guards)


@dataclass(frozen=True)
class ChangeSet:
    batch_id: str
    owner_id: str
    subject_id: str
    ops: tuple[FieldChange, ...]
    source_guards: tuple[SourceGuard, ...]

    @classmethod
    def from_documents(
        cls, before: dict[str, Any], after: dict[str, Any], *, batch_id: str, owner_id: str, subject_id: str
    ) -> "ChangeSet":
        if any(not isinstance(value, str) or not value.strip() for value in (batch_id, owner_id, subject_id)):
            raise ChangeConflict("整理批次与归属标识不能为空")
        validate_document(before, owner_id, subject_id)
        validate_document(after, owner_id, subject_id)
        ops = _operations(before, after)
        result = cls(batch_id, owner_id, subject_id, ops, _guards(before, ops))
        _check_sources(before, result)
        _check_topics(before, result)
        _check_topics(after, result)
        return result

    @property
    def inverse_ops(self) -> tuple[FieldChange, ...]:
        return tuple(op.inverse() for op in reversed(self.ops))

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "owner_id": self.owner_id,
            "subject_id": self.subject_id,
            "ops": [op.as_dict() for op in self.ops],
            "inverse_ops": [op.as_dict() for op in self.inverse_ops],
            "source_guards": [guard.as_dict() for guard in self.source_guards],
        }


def _check_sources(document: dict[str, Any], change_set: ChangeSet) -> None:
    scope(document, change_set.owner_id, change_set.subject_id)
    for guard in change_set.source_guards:
        record = records(document, guard.collection).get(guard.entity_id)
        if record is None:
            raise ChangeConflict("整理来源已不存在")
        scope(record, change_set.owner_id, change_set.subject_id)
        require_active(record)
        immutable = immutable_message(record) if guard.collection == "messages" else immutable_topic(record)
        if digest(immutable) != guard.immutable_digest:
            raise ChangeConflict("整理来源的原文或修订已变化")


def _check_topics(document: dict[str, Any], change_set: ChangeSet) -> None:
    for identity in {op.entity_id for op in change_set.ops if op.collection == "topics"}:
        record = records(document, "topics").get(identity)
        if record is not None:
            scope(record, change_set.owner_id, change_set.subject_id)
            require_active(record)


def _current(document: dict[str, Any], op: FieldChange) -> FieldValue:
    collection = records(document, op.collection)
    if op.field is None:
        return FieldValue.read(collection, op.entity_id)
    record = collection.get(op.entity_id)
    if record is None:
        raise ChangeConflict("整理目标已不存在")
    return FieldValue.read(record, op.field)


def _write(document: dict[str, Any], op: FieldChange) -> None:
    allowed = LABEL_FIELDS if op.collection == "messages" else TOPIC_FIELDS
    if op.collection not in {"messages", "topics"} or (op.field is not None and op.field not in allowed):
        raise ChangeConflict("整理操作包含不允许修改的字段")
    if op.field is None and (op.collection != "topics" or op.before.present == op.after.present):
        raise ChangeConflict("整理操作只能新增话题或撤销新话题")
    container = records(document, op.collection)
    key = op.entity_id
    if op.field is not None:
        container, key = container[op.entity_id], op.field
    if op.after.present:
        container[key] = op.after.value
    else:
        container.pop(key, None)


class MemoryChangeStore:
    """In-memory adapter with persistent-for-instance batch tombstones, never a production ledger."""

    def __init__(self, document: dict[str, Any]) -> None:
        self._owner_id = document.get("owner_id")
        self._subject_id = document.get("subject_id")
        if not isinstance(self._owner_id, str) or not isinstance(self._subject_id, str):
            raise ChangeConflict("整理快照缺少归属")
        validate_document(document, self._owner_id, self._subject_id)
        self._lock = RLock()
        self._document = deepcopy(document)
        self._batches: dict[str, tuple[str, ChangeSet, str]] = {}
        self._last_revert_conflicts: list[dict[str, Any]] = []

    @property
    def document(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._document)

    @property
    def last_revert_conflicts(self) -> list[dict[str, Any]]:
        """Only paths and reasons: skipped fields never leak original message values."""
        with self._lock:
            return deepcopy(self._last_revert_conflicts)

    def refresh(self, document: dict[str, Any]) -> None:
        """Load concurrent storage changes without erasing the batch replay tombstones."""
        with self._lock:
            validate_document(document, self._owner_id, self._subject_id)
            self._document = deepcopy(document)

    def apply(self, change_set: ChangeSet) -> dict[str, Any]:
        with self._lock:
            return self._apply(change_set)

    def _apply(self, change_set: ChangeSet) -> dict[str, Any]:
        scope(self._document, change_set.owner_id, change_set.subject_id)
        fingerprint = digest(change_set.as_dict())
        previous = self._batches.get(change_set.batch_id)
        if previous is not None:
            if previous[0] != fingerprint:
                raise ChangeConflict("同一整理批次不能更换内容")
            if previous[2] == "reverted":
                raise ChangeConflict("已撤销的整理批次不能重新应用")
            _check_sources(self._document, change_set)
            _check_topics(self._document, change_set)
            return self.document
        _check_sources(self._document, change_set)
        _check_topics(self._document, change_set)
        if any(_current(self._document, op) != op.before for op in change_set.ops):
            raise ChangeConflict("整理前置字段已变化，整批未应用")
        candidate = self.document
        for op in change_set.ops:
            _write(candidate, op)
        verified = ChangeSet.from_documents(
            self._document,
            candidate,
            batch_id=change_set.batch_id,
            owner_id=change_set.owner_id,
            subject_id=change_set.subject_id,
        )
        if verified != change_set:
            raise ChangeConflict("整理操作与来源防护不完整")
        validate_document(candidate, self._owner_id, self._subject_id)
        self._document = candidate
        self._batches[change_set.batch_id] = fingerprint, change_set, "applied"
        return self.document

    def revert(self, batch_id: str) -> dict[str, Any]:
        with self._lock:
            return self._revert(batch_id)

    def _revert(self, batch_id: str) -> dict[str, Any]:
        previous = self._batches.get(batch_id)
        if previous is None:
            raise ChangeConflict("整理批次不存在")
        fingerprint, change_set, state = previous
        scope(self._document, change_set.owner_id, change_set.subject_id)
        if state == "reverted":
            return self.document
        _check_sources(self._document, change_set)
        _check_topics(self._document, change_set)
        candidate = self.document
        conflicts = []
        for op in change_set.inverse_ops:
            if _current(candidate, op) == op.before:
                _write(candidate, op)
            else:
                conflicts.append(_conflict(batch_id, op, "field_changed"))
        for op in change_set.ops:
            if (
                op.collection == "topics"
                and op.field is None
                and op.entity_id not in candidate["topics"]
                and any(message.get("topic_id") == op.entity_id for message in candidate["messages"].values())
            ):
                candidate["topics"][op.entity_id] = deepcopy(self._document["topics"][op.entity_id])
                conflicts.append(_conflict(batch_id, op, "later_references"))
        validate_document(candidate, self._owner_id, self._subject_id)
        self._document = candidate
        self._last_revert_conflicts = conflicts
        self._batches[batch_id] = fingerprint, change_set, "reverted"
        return self.document


def _conflict(batch_id: str, op: FieldChange, reason: str) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "collection": op.collection,
        "entity_id": op.entity_id,
        "field": op.field,
        "reason": reason,
    }

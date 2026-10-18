"""Immutable, JSON-safe field changes; missing and explicit null remain distinct."""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

LABEL_FIELDS = frozenset({"space_id", "topic_id", "space_secondary", "route_source", "route_confidence"})
TOPIC_FIELDS = frozenset({"title", "space_id", "status", "message_ids"})
STOPPED_STATUSES = frozenset({"revoked", "withdrawn", "deleted"})


class ChangeConflict(ValueError):
    """The supplied snapshot no longer permits a safe label-only change."""


def canonical(value: Any) -> str:
    """Reject non-JSON data rather than silently coercing keys or losing values."""
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ChangeConflict("整理快照的字段名必须是字符串")
        for child in value.values():
            canonical(child)
    elif isinstance(value, list):
        for child in value:
            canonical(child)
    elif value is not None and type(value) not in {str, int, float, bool}:
        raise ChangeConflict("整理快照必须是 JSON 安全数据")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ChangeConflict("整理快照不能包含非有限数值")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FieldValue:
    present: bool
    encoded: str = "null"

    @classmethod
    def read(cls, document: dict[str, Any], key: str) -> "FieldValue":
        return cls(key in document, canonical(document.get(key)))

    @property
    def value(self) -> Any:
        return json.loads(self.encoded)

    def as_dict(self) -> dict[str, Any]:
        result = {"present": self.present}
        if self.present:
            result["value"] = self.value
        return result


@dataclass(frozen=True)
class FieldChange:
    collection: str
    entity_id: str
    field: str | None
    before: FieldValue
    after: FieldValue

    def inverse(self) -> "FieldChange":
        return FieldChange(self.collection, self.entity_id, self.field, self.after, self.before)

    def as_dict(self) -> dict[str, Any]:
        return {
            "collection": self.collection,
            "entity_id": self.entity_id,
            "field": self.field,
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
        }


@dataclass(frozen=True)
class SourceGuard:
    collection: str
    entity_id: str
    immutable_digest: str

    def as_dict(self) -> dict[str, str]:
        return {
            "collection": self.collection,
            "entity_id": self.entity_id,
            "immutable_digest": self.immutable_digest,
        }


def scope(document: dict[str, Any], owner_id: str, subject_id: str) -> None:
    if document.get("owner_id") != owner_id or document.get("subject_id") != subject_id:
        raise ChangeConflict("整理归属不匹配")


def require_active(record: dict[str, Any]) -> None:
    thread_id = record.get("thread_id", "")
    temporary = (
        record.get("incognito") is True
        or (isinstance(thread_id, str) and thread_id.startswith("incognito:"))
        or record.get("retention_scope", "persistent") != "persistent"
    )
    if temporary:
        raise ChangeConflict("无痕或临时来源不能写入持久化整理")
    statuses = [record.get(key) for key in ("status", "source_status")]
    if any(value is not None and not isinstance(value, str) for value in statuses):
        raise ChangeConflict("整理来源状态无效")
    stopped = any(value in STOPPED_STATUSES for value in statuses)
    if stopped or record.get("deleted_at") is not None or record.get("revoked_at") is not None:
        raise ChangeConflict("整理来源已停止使用")


def immutable_message(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in LABEL_FIELDS}


def immutable_topic(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in TOPIC_FIELDS}


def records(document: dict[str, Any], collection: str) -> dict[str, dict[str, Any]]:
    value = document.get(collection)
    if not isinstance(value, dict):
        raise ChangeConflict("整理快照缺少消息或话题集合")
    if any(not isinstance(record, dict) or record.get("id") != key for key, record in value.items()):
        raise ChangeConflict("整理快照的记录标识无效")
    return value


def validate_document(document: dict[str, Any], owner_id: str, subject_id: str) -> None:
    canonical(document)
    scope(document, owner_id, subject_id)
    for collection in ("messages", "topics"):
        for record in records(document, collection).values():
            scope(record, owner_id, subject_id)
    messages = records(document, "messages")
    topics = records(document, "topics")
    for message in messages.values():
        topic_id = message.get("topic_id")
        if topic_id in (None, ""):
            continue
        if not isinstance(topic_id, str) or topic_id not in topics:
            raise ChangeConflict("消息引用了不存在的话题，需要完整目录或先清洗旧数据")
        if "space_id" in message and message["space_id"] != topics[topic_id].get("space_id"):
            raise ChangeConflict("消息与所属话题的空间不一致")
    for topic in topics.values():
        message_ids = topic.get("message_ids", [])
        if not isinstance(message_ids, list) or any(not isinstance(value, str) for value in message_ids):
            raise ChangeConflict("话题消息列表无效")
        if len(set(message_ids)) != len(message_ids) or set(message_ids) - set(messages):
            raise ChangeConflict("话题引用了不存在或重复的消息")

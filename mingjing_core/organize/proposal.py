"""Editable suggestions, with explicit source snapshots for a later approved apply."""

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from .contracts import Message, MessageLabel, Topic, stable_id
from .local_vectors import keywords
from .spaces import DEFAULT_SPACES


@dataclass(frozen=True)
class Proposal:
    owner_id: str
    subject_id: str
    topics: tuple[Topic, ...]
    needs_review: tuple[str, ...]
    encoder_mode: str
    degradation: str | None
    messages: tuple[Message, ...] = field(repr=False)
    message_labels: tuple[MessageLabel, ...] = ()
    ignored_ids: tuple[str, ...] = ()

    def _topic(self, topic_id: str) -> Topic:
        found = next((topic for topic in self.topics if topic.id == topic_id), None)
        if found is None:
            raise ValueError("话题不存在")
        return found

    def _updated(self, removed: set[str], additions: tuple[Topic, ...]) -> "Proposal":
        result = replace(
            self,
            topics=tuple(topic for topic in self.topics if topic.id not in removed)
            + additions,
        )
        assigned = [
            message_id for topic in result.topics for message_id in topic.message_ids
        ]
        if len(assigned) != len(set(assigned)) or set(assigned) & set(self.ignored_ids):
            raise ValueError("话题归属重叠")
        return result

    def rename(self, topic_id: str, title: str) -> "Proposal":
        if not title.strip() or len(title) > 80:
            raise ValueError("话题名应为1至80字")
        return self._updated(
            {topic_id}, (replace(self._topic(topic_id), title=title.strip()),)
        )

    def move(self, topic_id: str, space_id: str) -> "Proposal":
        if space_id not in {space.id for space in DEFAULT_SPACES}:
            raise ValueError("未知功能区")
        return self._updated(
            {topic_id}, (replace(self._topic(topic_id), space_id=space_id),)
        )

    def merge(self, topic_ids: tuple[str, ...], title: str | None = None) -> "Proposal":
        if len(topic_ids) < 2 or len(set(topic_ids)) != len(topic_ids):
            raise ValueError("至少选择两个不同话题")
        topics = [self._topic(topic_id) for topic_id in topic_ids]
        if len({topic.space_id for topic in topics}) != 1:
            raise ValueError("合并前请先移到同一区")
        ids = {message_id for topic in topics for message_id in topic.message_ids}
        ordered = tuple(item.id for item in self.messages if item.id in ids)
        merged = self._rebuild(topics[0], ordered)
        result = self._updated(set(topic_ids), (merged,))
        return result.rename(merged.id, title) if title is not None else result

    def split(
        self, topic_id: str, message_ids: tuple[str, ...], title: str
    ) -> "Proposal":
        topic = self._topic(topic_id)
        selected = set(message_ids)
        if (
            len(selected) != len(message_ids)
            or not selected
            or not selected < set(topic.message_ids)
        ):
            raise ValueError("拆分需选择话题中部分不重复消息")
        old_ids = tuple(item for item in topic.message_ids if item not in selected)
        new_ids = tuple(item for item in topic.message_ids if item in selected)
        new_topic = replace(
            self._rebuild(topic, new_ids), id=stable_id("topic_", (topic.id, *new_ids))
        )
        result = self._updated({topic_id}, (self._rebuild(topic, old_ids), new_topic))
        return result.rename(new_topic.id, title)

    def ignore(self, topic_id: str) -> "Proposal":
        topic = self._topic(topic_id)
        result = self._updated({topic_id}, ())
        return replace(
            result,
            ignored_ids=tuple(sorted(set(self.ignored_ids) | set(topic.message_ids))),
        )

    def _rebuild(self, topic: Topic, message_ids: tuple[str, ...]) -> Topic:
        lookup = {message.id: message for message in self.messages}
        messages = [lookup[message_id] for message_id in message_ids]
        text = "\n".join(item.content for item in messages if item.role == "user")
        return replace(
            topic,
            message_ids=message_ids,
            start=messages[0].at_ms,
            end=messages[-1].at_ms,
            keywords=keywords(text),
            summary=text[:80],
        )

    def summary(self) -> dict[str, Any]:
        spaces = []
        for space in DEFAULT_SPACES:
            topics = [topic for topic in self.topics if topic.space_id == space.id]
            spaces.append(
                {
                    "space_id": space.id,
                    "name": space.name,
                    "sensitive": space.sensitive,
                    "message_count": sum(len(topic.message_ids) for topic in topics),
                    "topics": [
                        {
                            "id": topic.id,
                            "title": topic.title,
                            "message_count": len(topic.message_ids),
                            "start": topic.start,
                            "end": topic.end,
                            "sample": topic.summary[:80],
                        }
                        for topic in topics
                    ],
                }
            )
        return {
            "spaces": spaces,
            "needs_review": list(self.needs_review),
            "ignored": len(self.ignored_ids),
            "encoder_mode": self.encoder_mode,
            "degradation": self.degradation,
        }

    def to_changeset(self, document: Mapping[str, Any], batch_id: str) -> Any:
        from .changes import ChangeSet

        if (document.get("owner_id"), document.get("subject_id")) != (
            self.owner_id,
            self.subject_id,
        ):
            raise ValueError("整理建议归属不一致")
        target = copy.deepcopy(dict(document))
        self._check_source(document)
        topic_data = target.setdefault("topics", {})
        labels = {label.message_id: label for label in self.message_labels}
        for topic in self.topics:
            if topic.id in topic_data:
                raise ValueError("新话题标识已被占用")
            topic_data[topic.id] = {
                "id": topic.id,
                "owner_id": self.owner_id,
                "subject_id": self.subject_id,
                "title": topic.title,
                "space_id": topic.space_id,
                "message_ids": list(topic.message_ids),
                "status": "open",
            }
            for message_id in topic.message_ids:
                label = labels.get(message_id)
                manually_moved = label is None or label.space_id != topic.space_id
                target["messages"][message_id].update(
                    {
                        "space_id": topic.space_id,
                        "topic_id": topic.id,
                        "space_secondary": None if manually_moved else label.secondary,
                        "route_source": "user" if manually_moved else "migration",
                        "route_confidence": 1.0 if manually_moved else label.confidence,
                    }
                )
        return ChangeSet.from_documents(
            dict(document),
            target,
            batch_id=batch_id,
            owner_id=self.owner_id,
            subject_id=self.subject_id,
        )

    def _check_source(self, document: Mapping[str, Any]) -> None:
        lookup = document.get("messages", {})
        for message in self.messages:
            current = lookup.get(message.id)
            if current is None or any(
                current.get(name) != getattr(message, name)
                for name in ("owner_id", "subject_id", "content", "at_ms", "role")
            ):
                raise ValueError("原始消息已变化，请重新整理")
            if (
                current.get("revision", 1) != message.revision
                or current.get("status", "active") != message.status
            ):
                raise ValueError("原始消息修订已变化，请重新整理")

"""Immutable inputs; expected labels and storage writes never enter the engine."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Message:
    id: str
    role: Literal["user", "assistant"]
    content: str = field(repr=False)
    at_ms: int
    owner_id: str
    subject_id: str
    revision: int = 1
    status: str = "active"
    incognito: bool = False
    thread_id: str = ""
    retention_scope: str = "persistent"

    def __post_init__(self) -> None:
        if not self.id or not self.owner_id or not self.subject_id:
            raise ValueError("消息缺少有效归属")
        if (
            self.role not in {"user", "assistant"}
            or isinstance(self.at_ms, bool)
            or not isinstance(self.at_ms, int)
        ):
            raise ValueError("消息格式无效")
        if (
            not isinstance(self.content, str)
            or type(self.revision) is not int
            or self.revision < 1
        ):
            raise ValueError("消息正文或修订格式无效")


@dataclass(frozen=True)
class Segment:
    id: str
    message_ids: tuple[str, ...]
    start: int
    end: int
    keywords: tuple[str, ...]
    text: str = field(repr=False)
    user_text: str = field(repr=False)


@dataclass(frozen=True)
class SpaceDecision:
    space_id: str
    confidence: float
    needs_review: bool
    secondary: str | None = None
    source: Literal["rule", "embedding"] = "rule"


@dataclass(frozen=True)
class MessageLabel:
    message_id: str
    space_id: str
    secondary: str | None
    confidence: float
    needs_review: bool


@dataclass(frozen=True)
class Topic:
    id: str
    space_id: str
    title: str = field(repr=False)
    segment_ids: tuple[str, ...]
    message_ids: tuple[str, ...]
    start: int
    end: int
    keywords: tuple[str, ...]
    summary: str = field(repr=False)


@dataclass(frozen=True)
class RouteDecision:
    space_id: str
    topic_id: str | None
    confidence: float
    source: Literal["rule", "embedding", "sticky", "user"]
    needs_review: bool = False


@dataclass(frozen=True)
class TopicCatalog:
    owner_id: str
    subject_id: str
    topics: tuple[Topic, ...]

    def __post_init__(self) -> None:
        if (
            not self.owner_id
            or not self.subject_id
            or len({item.id for item in self.topics}) != len(self.topics)
        ):
            raise ValueError("话题目录无效")


def stable_id(prefix: str, values: tuple[str, ...]) -> str:
    import hashlib
    import json

    raw = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()
    return prefix + hashlib.sha256(raw).hexdigest()[:24]

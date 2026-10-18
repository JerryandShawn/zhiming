"""Ordered, scope-safe segmentation; assistant replies stay with their user turn."""

from collections.abc import Sequence

from .contracts import Message, Segment, stable_id
from .local_vectors import KeywordVectorizer, Vectorizer, cosine, keywords


def validate_messages(messages: Sequence[Message]) -> None:
    if any(item.status != "active" for item in messages):
        raise ValueError("不能整理已撤回或无效来源")
    if any(
        item.incognito or item.thread_id.startswith("incognito:") or item.retention_scope != "persistent"
        for item in messages
    ):
        raise ValueError("不能把临时或无痕来源整理到长期话题")
    if len({item.id for item in messages}) != len(messages):
        raise ValueError("消息标识重复")
    if len({(item.owner_id, item.subject_id) for item in messages}) > 1:
        raise ValueError("不能跨归属整理消息")
    if any(left.at_ms > right.at_ms for left, right in zip(messages, messages[1:], strict=False)):
        raise ValueError("消息需要按时间排序")


def _segment(messages: list[Message]) -> Segment:
    ids = tuple(item.id for item in messages)
    user_text = "\n".join(item.content for item in messages if item.role == "user")
    text = "\n".join(item.content for item in messages)
    identity = (messages[0].owner_id, messages[0].subject_id, *ids)
    return Segment(
        stable_id("seg_", identity), ids, messages[0].at_ms, messages[-1].at_ms, keywords(user_text), text, user_text
    )


class Segmenter:
    def __init__(
        self, vectorizer: Vectorizer | None = None, gap_hours: float = 6, turn_threshold: float = 0.22
    ) -> None:
        if gap_hours <= 0 or not 0 <= turn_threshold <= 1:
            raise ValueError("切段参数无效")
        self.vectorizer = vectorizer or KeywordVectorizer()
        self.gap_ms = gap_hours * 3_600_000
        self.turn_threshold = turn_threshold

    def segment(self, messages: Sequence[Message]) -> tuple[Segment, ...]:
        validate_messages(messages)
        output: list[Segment] = []
        current: list[Message] = []
        recent_users: list[str] = []
        for message in messages:
            gap = bool(current) and message.at_ms - current[-1].at_ms > self.gap_ms
            shift = self._shift(message, recent_users)
            if current and (gap or shift):
                output.append(_segment(current))
                current, recent_users = [], []
            current.append(message)
            if message.role == "user":
                recent_users.append(message.content)
                recent_users = recent_users[-2:]
        if current:
            output.append(_segment(current))
        return tuple(output)

    def _shift(self, message: Message, recent_users: list[str]) -> bool:
        if message.role != "user" or not recent_users:
            return False
        previous = self.vectorizer.encode("\n".join(recent_users))
        candidate = self.vectorizer.encode(message.content)
        if not previous or not candidate:
            return False
        # Short acknowledgements have insufficient evidence to create a new topic.
        if len(message.content.strip()) < 8 and not keywords(message.content):
            return False
        return cosine(previous, candidate) < self.turn_threshold
